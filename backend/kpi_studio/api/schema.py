"""Schema explorer endpoints — Phase 1 (SuperAdmin diagnostic).

Three endpoints:
  GET  /schema/tables   → latest snapshot's tables (auto-introspects on first call)
  GET  /schema/graph    → nodes/edges projection for the ER diagram
  POST /schema/refresh  → re-introspect now and persist a new snapshot

Routes are registered inside ``build_router()`` so ``Depends(...)`` captures
the already-bound host auth dep, not the placeholder. See router.py.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import KpiTableRelationship
from kpi_studio.schemas import (
    SchemaGraph, SchemaListResponse, SchemaRefreshResponse, SchemaSnapshotMeta,
    TableRelationshipAutoSeedResponse, TableRelationshipCreate,
    TableRelationshipListResponse, TableRelationshipPayload,
)
from kpi_studio.services import introspector, relationship_service


def _meta(snap) -> SchemaSnapshotMeta:
    return SchemaSnapshotMeta(
        snapshot_id=snap.snapshot_id,
        database_key=snap.database_key,
        table_count=snap.table_count,
        relationship_count=snap.relationship_count,
        created_at=snap.created_at,
        created_by=snap.created_by,
        is_current=snap.is_current,
    )


def _user_id(user: Any) -> int | None:
    for attr in ("user_id", "id", "userId"):
        val = getattr(user, attr, None)
        if isinstance(val, int):
            return val
    return None


def _ensure_snapshot(db: Session, user: Any):
    snap = introspector.get_current_snapshot(db)
    if snap is None:
        cfg = deps.get_config()
        payload = introspector.reflect_schema(cfg.target_engine, cfg)
        snap = introspector.persist_snapshot(db, payload, created_by=_user_id(user))
    return snap


def build_router() -> APIRouter:
    """Build the schema-explorer router. Called by ``create_router`` after
    ``bind_config`` so all ``Depends(...)`` calls capture the live host
    auth dep instead of the placeholder."""
    router = APIRouter()

    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "/tables",
        response_model=SchemaListResponse,
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def list_tables(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> SchemaListResponse:
        snap = _ensure_snapshot(db, user)
        payload = introspector.load_payload(snap)
        return SchemaListResponse(snapshot=_meta(snap), tables=payload.tables)

    @router.get(
        "/graph",
        response_model=SchemaGraph,
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def get_graph(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> SchemaGraph:
        snap = _ensure_snapshot(db, user)
        payload = introspector.load_payload(snap)
        return introspector.build_graph(payload)

    @router.post(
        "/refresh",
        response_model=SchemaRefreshResponse,
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def refresh_schema(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> SchemaRefreshResponse:
        cfg = deps.get_config()
        try:
            payload = introspector.reflect_schema(cfg.target_engine, cfg)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Schema introspection failed: {exc}",
            )
        snap = introspector.persist_snapshot(db, payload, created_by=_user_id(user))
        return SchemaRefreshResponse(snapshot=_meta(snap), refreshed=True)

    # ---- Phase F — Table relationships -------------------------------

    def _to_rel_payload(r: KpiTableRelationship) -> TableRelationshipPayload:
        return TableRelationshipPayload(
            relationship_id=r.relationship_id,
            company_id=r.company_id,
            from_schema=r.from_schema,
            from_table=r.from_table,
            from_column=r.from_column,
            to_schema=r.to_schema,
            to_table=r.to_table,
            to_column=r.to_column,
            cardinality=r.cardinality,  # type: ignore[arg-type]
            source=r.source,  # type: ignore[arg-type]
            is_active=r.is_active,
        )

    @router.get(
        "/relationships",
        response_model=TableRelationshipListResponse,
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def list_relationships(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> TableRelationshipListResponse:
        # Global rows only for now (company_id=None) — multi-tenant
        # overrides land when a tenant resolver is wired through.
        rows = relationship_service.list_relationships(db, company_id=None)
        items = [_to_rel_payload(r) for r in rows]
        return TableRelationshipListResponse(items=items, total=len(items))

    @router.post(
        "/relationships",
        response_model=TableRelationshipPayload,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def create_relationship(
        payload: TableRelationshipCreate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> TableRelationshipPayload:
        rel = relationship_service.create_manual_relationship(
            db,
            from_schema=payload.from_schema,
            from_table=payload.from_table,
            from_column=payload.from_column,
            to_schema=payload.to_schema,
            to_table=payload.to_table,
            to_column=payload.to_column,
            cardinality=payload.cardinality,
            company_id=None,
            created_by=_user_id(user),
        )
        return _to_rel_payload(rel)

    @router.delete(
        "/relationships/{relationship_id}",
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def delete_relationship(
        relationship_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        rel = relationship_service.get_relationship(db, relationship_id)
        if rel is None:
            raise HTTPException(status_code=404, detail="Relationship not found.")
        relationship_service.soft_delete_relationship(db, rel)
        return {"deleted": True, "relationship_id": relationship_id}

    @router.post(
        "/relationships/auto-seed",
        response_model=TableRelationshipAutoSeedResponse,
        dependencies=[Depends(perm("kpi:schema"))],
    )
    def auto_seed_relationships(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> TableRelationshipAutoSeedResponse:
        snap = _ensure_snapshot(db, user)
        payload = introspector.load_payload(snap)
        result = relationship_service.auto_seed_from_schema(
            db, payload, company_id=None,
        )
        return TableRelationshipAutoSeedResponse(
            inserted=result.inserted,
            skipped=result.skipped,
            total_active=result.total_active,
        )

    return router
