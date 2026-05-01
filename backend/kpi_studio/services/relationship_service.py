"""Table-relationship service (Phase F — data modeling).

Edges are seeded from FK metadata via the introspector's
``SchemaPayload`` and stored on ``KpiTableRelationship``. The compiler
walks them at query-build time to auto-emit ``LEFT JOIN``s when a
BuilderField references a column from a related table.

The auto-seed pass is idempotent: existing ``source='auto'`` rows are
preserved if they still match a current FK, replaced if the FK
target changed, and removed when the FK was dropped from the schema.
``source='manual'`` rows are never touched.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from kpi_studio.models import KpiTableRelationship
from kpi_studio.schemas import SchemaPayload


@dataclass
class AutoSeedResult:
    inserted: int
    skipped: int   # already-present rows that matched the FK exactly
    total_active: int


def list_relationships(
    db: Session,
    *,
    company_id: Optional[int] = None,
    include_inactive: bool = False,
) -> List[KpiTableRelationship]:
    """Per-tenant list. ``company_id=None`` rows are global — they
    apply to every tenant and always come back too."""
    q = db.query(KpiTableRelationship)
    if not include_inactive:
        q = q.filter(KpiTableRelationship.is_active == True)  # noqa: E712
    # Tenant-scoped + global rows.
    if company_id is None:
        q = q.filter(KpiTableRelationship.company_id.is_(None))
    else:
        q = q.filter(
            (KpiTableRelationship.company_id == company_id)
            | (KpiTableRelationship.company_id.is_(None))
        )
    return q.order_by(
        KpiTableRelationship.from_table,
        KpiTableRelationship.from_column,
    ).all()


def get_relationship(
    db: Session, relationship_id: int,
) -> Optional[KpiTableRelationship]:
    return (
        db.query(KpiTableRelationship)
        .filter(KpiTableRelationship.relationship_id == relationship_id)
        .first()
    )


def create_manual_relationship(
    db: Session,
    *,
    from_schema: Optional[str], from_table: str, from_column: str,
    to_schema: Optional[str], to_table: str, to_column: str,
    cardinality: str = "many_to_one",
    company_id: Optional[int] = None,
    created_by: Optional[int] = None,
) -> KpiTableRelationship:
    """Create a user-defined edge. Manual rows are never touched by
    the auto-seed pass, so customizations survive schema reflection."""
    rel = KpiTableRelationship(
        company_id=company_id,
        from_schema=from_schema,
        from_table=from_table,
        from_column=from_column,
        to_schema=to_schema,
        to_table=to_table,
        to_column=to_column,
        cardinality=cardinality,
        source="manual",
        is_active=True,
        created_by=created_by,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def soft_delete_relationship(db: Session, rel: KpiTableRelationship) -> None:
    rel.is_active = False
    db.commit()


def auto_seed_from_schema(
    db: Session,
    schema: SchemaPayload,
    *,
    company_id: Optional[int] = None,
) -> AutoSeedResult:
    """Walk every table's ``foreign_keys`` and reconcile against the
    DB.

    * ``many_to_one`` is emitted for each FK constraint.
    * Pre-existing matching auto rows: skipped (idempotent).
    * Auto rows whose FK no longer exists: deactivated (set
      ``is_active=False``) so the spec compiler stops resolving them.
    * Manual rows are left alone.
    """
    discovered: list[tuple] = []
    for table in schema.tables:
        for fk in table.foreign_keys:
            if not fk.constrained_columns or not fk.referred_columns:
                continue
            # Composite FKs are unusual in BI schemas; for now we only
            # represent single-column edges. Composite rendering can
            # come later as a separate "join_condition" string column.
            if len(fk.constrained_columns) != 1:
                continue
            discovered.append((
                table.schema_name, table.name, fk.constrained_columns[0],
                fk.referred_schema, fk.referred_table, fk.referred_columns[0],
            ))

    # Existing auto rows for this tenant scope.
    existing_q = db.query(KpiTableRelationship).filter(
        KpiTableRelationship.source == "auto",
        KpiTableRelationship.company_id.is_(company_id),
    )
    existing_map = {
        _edge_key(r): r for r in existing_q.all()
    }
    discovered_keys = {_edge_key_tuple(t) for t in discovered}

    inserted = 0
    skipped = 0
    for tup in discovered:
        key = _edge_key_tuple(tup)
        existing = existing_map.get(key)
        if existing is not None:
            # Re-activate if previously deactivated, otherwise no-op.
            if not existing.is_active:
                existing.is_active = True
            skipped += 1
            continue
        from_schema, from_table, from_column, to_schema, to_table, to_column = tup
        db.add(KpiTableRelationship(
            company_id=company_id,
            from_schema=from_schema,
            from_table=from_table,
            from_column=from_column,
            to_schema=to_schema,
            to_table=to_table,
            to_column=to_column,
            cardinality="many_to_one",
            source="auto",
            is_active=True,
        ))
        inserted += 1

    # Edges no longer in the schema → deactivate (preserves history).
    for key, rel in existing_map.items():
        if key not in discovered_keys and rel.is_active:
            rel.is_active = False

    db.commit()

    total_active = (
        db.query(KpiTableRelationship)
        .filter(KpiTableRelationship.is_active == True)  # noqa: E712
        .count()
    )
    return AutoSeedResult(inserted=inserted, skipped=skipped, total_active=total_active)


# ---------------------------------------------------------------------------
# Graph helpers — used by the spec compiler at query-build time
# ---------------------------------------------------------------------------

def find_path(
    relationships: Iterable[KpiTableRelationship],
    *,
    from_table: str,
    to_table: str,
    from_schema: Optional[str] = None,
    to_schema: Optional[str] = None,
    max_depth: int = 4,
) -> Optional[List[KpiTableRelationship]]:
    """Find the shortest sequence of join edges that connects two
    tables. Returns the path as a list of ``KpiTableRelationship`` rows
    (each consumed as a ``LEFT JOIN``), or ``None`` if no path exists
    within ``max_depth`` hops.

    Direction-agnostic: an edge ``A → B`` can be traversed both ways
    (the compiler emits ``A.col = B.col`` regardless), so a fact-table
    join chain like enquiries → customers → companies works whether
    the FKs are stored bottom-up or top-down.
    """
    if (from_schema or "", from_table) == (to_schema or "", to_table):
        return []

    # Build adjacency: each table → list of (neighbor, edge).
    adj: dict[tuple[str, str], list[tuple[tuple[str, str], KpiTableRelationship]]] = {}
    for r in relationships:
        if not r.is_active:
            continue
        a = (r.from_schema or "", r.from_table)
        b = (r.to_schema or "", r.to_table)
        adj.setdefault(a, []).append((b, r))
        adj.setdefault(b, []).append((a, r))

    src = (from_schema or "", from_table)
    dst = (to_schema or "", to_table)
    # BFS for shortest path.
    queue: list[tuple[tuple[str, str], list[KpiTableRelationship]]] = [(src, [])]
    visited = {src}
    while queue:
        node, path = queue.pop(0)
        if len(path) > max_depth:
            continue
        for neighbor, edge in adj.get(node, []):
            if neighbor in visited:
                continue
            new_path = path + [edge]
            if neighbor == dst:
                return new_path
            visited.add(neighbor)
            queue.append((neighbor, new_path))
    return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _edge_key(r: KpiTableRelationship) -> tuple:
    return (
        r.from_schema or "", r.from_table, r.from_column,
        r.to_schema or "", r.to_table, r.to_column,
    )


def _edge_key_tuple(t: tuple) -> tuple:
    fs, ft, fc, ts, tt, tc = t
    return (fs or "", ft, fc, ts or "", tt, tc)


__all__ = [
    "AutoSeedResult",
    "list_relationships",
    "get_relationship",
    "create_manual_relationship",
    "soft_delete_relationship",
    "auto_seed_from_schema",
    "find_path",
]
