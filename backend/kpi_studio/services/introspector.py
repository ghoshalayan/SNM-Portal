"""Schema introspector — reflects DB metadata into a serialisable snapshot.

Pure SQLAlchemy ``Inspector`` calls, plus filtering driven by
``KpiStudioConfig``. Snapshots are persisted to ``kpi_schema_snapshot`` so
the UI can serve the latest cached version without re-reflecting every
page load (which is slow on SQL Server with hundreds of tables).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from kpi_studio.config import KpiStudioConfig
from kpi_studio.models import KpiSchemaSnapshot
from kpi_studio.schemas import (
    ColumnInfo, ForeignKeyInfo, GraphEdge, GraphNode, IndexInfo,
    SchemaGraph, SchemaPayload, TableInfo,
)

log = logging.getLogger(__name__)


def _column_info(col: dict) -> ColumnInfo:
    return ColumnInfo(
        name=col["name"],
        type=str(col.get("type", "")),
        nullable=bool(col.get("nullable", True)),
        primary_key=bool(col.get("primary_key", False)),
        default=str(col["default"]) if col.get("default") is not None else None,
        autoincrement=bool(col.get("autoincrement", False)),
        comment=col.get("comment"),
    )


def reflect_schema(engine: Engine, cfg: KpiStudioConfig) -> SchemaPayload:
    """Introspect the engine's database and return a serialisable payload.

    Does not touch the kpi_schema_snapshot table — call ``persist_snapshot``
    for that. Splitting them makes the function easy to unit-test against
    SQLite without needing the kpi_ tables.
    """
    inspector = inspect(engine)
    tables: list[TableInfo] = []

    schemas = inspector.get_schema_names()
    for schema_name in schemas:
        if schema_name in cfg.excluded_schemas:
            continue

        for table_name in inspector.get_table_names(schema=schema_name):
            if not cfg.is_table_visible(table_name):
                continue

            try:
                columns = [_column_info(c) for c in inspector.get_columns(table_name, schema=schema_name)]
                pk = inspector.get_pk_constraint(table_name, schema=schema_name)
                fks = inspector.get_foreign_keys(table_name, schema=schema_name)
                idxs = inspector.get_indexes(table_name, schema=schema_name)
                comment = None
                try:
                    comment_dict = inspector.get_table_comment(table_name, schema=schema_name)
                    comment = (comment_dict or {}).get("text")
                except NotImplementedError:
                    pass

                tables.append(TableInfo(
                    schema=schema_name,
                    name=table_name,
                    comment=comment,
                    columns=columns,
                    primary_key=list(pk.get("constrained_columns", []) or []),
                    foreign_keys=[
                        ForeignKeyInfo(
                            constrained_columns=list(fk.get("constrained_columns", []) or []),
                            referred_schema=fk.get("referred_schema"),
                            referred_table=fk.get("referred_table", ""),
                            referred_columns=list(fk.get("referred_columns", []) or []),
                            name=fk.get("name"),
                        )
                        for fk in fks
                    ],
                    indexes=[
                        IndexInfo(
                            name=i.get("name") or "",
                            columns=list(i.get("column_names", []) or []),
                            unique=bool(i.get("unique", False)),
                        )
                        for i in idxs
                    ],
                ))
            except Exception as exc:  # one bad table shouldn't kill the whole reflection
                log.warning("kpi_studio: skipped table %s.%s: %s", schema_name, table_name, exc)

    # Stable ordering — schema first, then table — so JSON snapshots diff cleanly.
    tables.sort(key=lambda t: ((t.schema_name or ""), t.name))

    return SchemaPayload(
        dialect=engine.dialect.name,
        database_key="primary",
        introspected_at=datetime.now(timezone.utc),
        tables=tables,
    )


def build_graph(payload: SchemaPayload) -> SchemaGraph:
    """Project the payload into a (nodes, edges) graph suitable for vis-network."""
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    for t in payload.tables:
        node_id = _qualify(t.schema_name, t.name)
        nodes[node_id] = GraphNode(
            id=node_id,
            label=t.name,
            schema=t.schema_name,
            column_count=len(t.columns),
        )

    for t in payload.tables:
        src = _qualify(t.schema_name, t.name)
        for fk in t.foreign_keys:
            tgt = _qualify(fk.referred_schema or t.schema_name, fk.referred_table)
            # Skip dangling FKs (referenced table excluded from snapshot).
            if tgt not in nodes:
                continue
            edges.append(GraphEdge(
                source=src,
                target=tgt,
                columns=fk.constrained_columns,
                name=fk.name,
            ))

    return SchemaGraph(nodes=list(nodes.values()), edges=edges)


def _qualify(schema_name: Optional[str], table: str) -> str:
    return f"{schema_name}.{table}" if schema_name else table


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_snapshot(
    db: Session,
    payload: SchemaPayload,
    *,
    created_by: Optional[int] = None,
) -> KpiSchemaSnapshot:
    """Insert a new snapshot row and demote prior current-flag rows for the
    same database_key. The whole thing runs in one transaction."""
    relationship_count = sum(len(t.foreign_keys) for t in payload.tables)

    # Demote any existing current snapshot for this database_key.
    # NOTE: ``== True`` (not ``.is_(True)``) — SQL Server rejects ``IS 1``
    # because the ``IS`` operator is reserved for ``IS NULL`` in T-SQL.
    db.query(KpiSchemaSnapshot).filter(
        KpiSchemaSnapshot.database_key == payload.database_key,
        KpiSchemaSnapshot.is_current == True,  # noqa: E712 — SQLAlchemy needs ==, not is
    ).update({"is_current": False}, synchronize_session=False)

    snapshot = KpiSchemaSnapshot(
        database_key=payload.database_key,
        payload=payload.model_dump(mode="json", by_alias=True),
        table_count=len(payload.tables),
        relationship_count=relationship_count,
        created_at=datetime.now(timezone.utc),
        created_by=created_by,
        is_current=True,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_current_snapshot(
    db: Session, database_key: str = "primary",
) -> Optional[KpiSchemaSnapshot]:
    return (
        db.query(KpiSchemaSnapshot)
        .filter(
            KpiSchemaSnapshot.database_key == database_key,
            KpiSchemaSnapshot.is_current == True,  # noqa: E712 — see persist_snapshot
        )
        .order_by(KpiSchemaSnapshot.created_at.desc())
        .first()
    )


def load_payload(snapshot: KpiSchemaSnapshot) -> SchemaPayload:
    return SchemaPayload.model_validate(snapshot.payload)
