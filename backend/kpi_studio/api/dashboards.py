"""Dashboards CRUD + items + layout + assignments.

Endpoints:
  GET    /dashboards                                list (mine + shared + assigned)
  POST   /dashboards                                create
  GET    /dashboards/{id}                           detail with items
  PUT    /dashboards/{id}                           patch metadata
  DELETE /dashboards/{id}                           soft delete
  POST   /dashboards/{id}/items                     add a KPI to the board
  PUT    /dashboards/{id}/items/{itemId}            patch a single item (size / title)
  DELETE /dashboards/{id}/items/{itemId}            remove
  PUT    /dashboards/{id}/layout                    bulk update positions (drag-drop end)
  POST   /dashboards/{id}/auto-decorate             AI proposes a tidier layout (J.2)
  GET    /dashboards/{id}/assignments               list role/user grants  (A4)
  POST   /dashboards/{id}/assignments               grant role or user     (A4)
  DELETE /dashboards/{id}/assignments/{aid}         revoke                 (A4)

Routes are registered inside ``build_router`` for the same reason as
``api/kpis.py`` — see comment there.
"""
from __future__ import annotations

import os
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from kpi_studio import deps
from kpi_studio.models import (
    CARD_SIZES, DASHBOARD_SCOPE_COMPANY, DASHBOARD_SCOPE_USER,
    KpiDashboard, KpiDashboardAssignment, KpiDashboardItem, KpiDefinition,
)
from kpi_studio.providers.llm.base import LlmProviderError
from kpi_studio.schemas import (
    DASHBOARD_ANIMATIONS, BuilderFilter, BuilderSpec,
    DashboardAssignmentCreate, DashboardAssignmentInfo,
    ChartConfig, DashboardCreate, DashboardDecorateResponse,
    DashboardDecorationItem, DashboardDetail, DashboardItemCreate,
    DashboardItemPayload, DashboardItemUpdate, DashboardLayoutRequest,
    DashboardListResponse, DashboardSummary, DashboardUpdate,
)
from kpi_studio.services import dashboard_decorator, settings_service


_VALID_SCOPES = (DASHBOARD_SCOPE_USER, DASHBOARD_SCOPE_COMPANY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _company_id(user: Any) -> Optional[int]:
    cfg = deps.get_config()
    if cfg.tenant_resolver is None:
        return None
    try:
        return cfg.tenant_resolver(user)
    except Exception:
        return None


def _is_super_admin(user: Any) -> bool:
    return bool(getattr(user, "is_super_admin", False))


def _role_id(user: Any) -> Optional[int]:
    """Best-effort extraction of the caller's active role id.

    Used for visibility checks against role-based assignments. The host's
    JWT places ``role_id`` on the ``CurrentUser`` dataclass; we duck-type
    rather than import.
    """
    for attr in ("role_id", "roleId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _scope_query(q, user: Any):
    """Limit a dashboard query to rows the caller can see.

    Visibility:
      * SuperAdmin → all
      * Otherwise →
          owner_user_id == me
          OR (scope == company AND company_id == mine)
          OR EXISTS an assignment for me (user_id) or my role (role_id)
    """
    if _is_super_admin(user):
        return q
    uid = _user_id(user)
    cid = _company_id(user)
    rid = _role_id(user)

    # Subquery — dashboard ids the caller has been explicitly granted via
    # an assignment row (either by user-id or by role-id). Cheap because
    # ``dashboard_id`` is indexed on the assignments table.
    assigned_dash_ids = (
        select(KpiDashboardAssignment.dashboard_id)
        .where(
            or_(
                KpiDashboardAssignment.user_id == uid,
                KpiDashboardAssignment.role_id == rid,
            )
        )
    )

    return q.filter(
        or_(
            KpiDashboard.owner_user_id == uid,
            (KpiDashboard.scope == DASHBOARD_SCOPE_COMPANY) & (KpiDashboard.company_id == cid),
            KpiDashboard.dashboard_id.in_(assigned_dash_ids),
        )
    )


def _can_view(dashboard: KpiDashboard, user: Any) -> bool:
    """View permission. Reads ``dashboard.assignments`` so the caller
    must have eager-loaded the relationship before calling."""
    if _is_super_admin(user):
        return True
    uid = _user_id(user)
    cid = _company_id(user)
    rid = _role_id(user)
    if dashboard.owner_user_id == uid:
        return True
    if dashboard.scope == DASHBOARD_SCOPE_COMPANY and dashboard.company_id == cid:
        return True
    # Assignment grants — either to this user directly, or to their role.
    for a in (dashboard.assignments or []):
        if a.user_id is not None and a.user_id == uid:
            return True
        if a.role_id is not None and a.role_id == rid:
            return True
    return False


def _can_edit(dashboard: KpiDashboard, user: Any) -> bool:
    """Edit permission.

    * SuperAdmin → always
    * Owner of the dashboard → always
    * Same-company author → can edit shared (company-scope) dashboards too,
      so a team can collaborate on a shared board.
    """
    if _is_super_admin(user):
        return True
    uid = _user_id(user)
    cid = _company_id(user)
    if dashboard.owner_user_id == uid:
        return True
    if dashboard.scope == DASHBOARD_SCOPE_COMPANY and dashboard.company_id == cid:
        return True
    return False


def _can_delete(dashboard: KpiDashboard, user: Any) -> bool:
    """Only the original owner or SuperAdmin can delete (even shared boards).

    Anyone-can-edit + anyone-can-delete = chaos for shared dashboards. Edit
    is permissive; delete stays owner-only.
    """
    if _is_super_admin(user):
        return True
    return dashboard.owner_user_id == _user_id(user)


def _can_manage_assignments(dashboard: KpiDashboard, user: Any) -> bool:
    """Who can grant / revoke assignments. Per the user's spec: from
    SuperAdmin only. Owner is also allowed so they can self-share without
    an admin being in the loop.
    """
    if _is_super_admin(user):
        return True
    return dashboard.owner_user_id == _user_id(user)


def _validate_scope(scope: str) -> str:
    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope '{scope}'. Must be one of {_VALID_SCOPES}.",
        )
    return scope


def _validate_size(size: str) -> str:
    if size not in CARD_SIZES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid size '{size}'. Must be one of {CARD_SIZES}.",
        )
    return size


def _validate_animation(value: Optional[str]) -> Optional[str]:
    """Coerce an animation override. Empty string clears it; None
    leaves it unchanged (caller's responsibility). Unknown values are
    rejected so a typo in the LLM proposal can't poison the row."""
    if value is None:
        return None
    if value == "":
        return ""  # sentinel — caller maps to None
    if value not in DASHBOARD_ANIMATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid animation '{value}'. Must be one of {DASHBOARD_ANIMATIONS}.",
        )
    return value


def _filters_to_json(filters: Optional[List[BuilderFilter]]) -> Optional[list]:
    """Serialise a list of BuilderFilter into the JSON shape we store
    in ``filters_json``. ``None`` means "leave unchanged"; an empty
    list clears the override."""
    if filters is None:
        return None
    return [f.model_dump(by_alias=True) for f in filters]


def _filters_from_json(value: Any) -> List[BuilderFilter]:
    """Re-hydrate the stored JSON list back into BuilderFilter objects.
    Defensive — a corrupted row should yield an empty list rather
    than break the response."""
    if not value:
        return []
    if not isinstance(value, list):
        return []
    out: List[BuilderFilter] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        try:
            out.append(BuilderFilter.model_validate(raw))
        except Exception:
            continue
    return out


def _to_summary(d: KpiDashboard, item_count: int) -> DashboardSummary:
    return DashboardSummary(
        dashboard_id=d.dashboard_id,
        name=d.name,
        description=d.description,
        scope=d.scope,
        owner_user_id=d.owner_user_id,
        company_id=d.company_id,
        is_active=d.is_active,
        item_count=item_count,
        updated_at=d.updated_at,
    )


def _kpi_builder_specs(db: Session, kpi_ids: set[int]) -> dict[int, Optional[BuilderSpec]]:
    """Bulk-fetch each KPI's saved BuilderSpec (current version).
    Raw-SQL KPIs return ``None`` for that key — the decorator
    interprets ``None`` as "skip filter proposals for this card"."""
    if not kpi_ids:
        return {}
    rows = (
        db.query(KpiDefinition)
        .options(selectinload(KpiDefinition.versions))
        .filter(KpiDefinition.kpi_id.in_(kpi_ids))
        .all()
    )
    out: dict[int, Optional[BuilderSpec]] = {}
    for k in rows:
        spec: Optional[BuilderSpec] = None
        if k.current_version_id and k.versions:
            current = next(
                (v for v in k.versions if v.version_id == k.current_version_id),
                None,
            )
            if current and isinstance(current.builder_spec, dict):
                try:
                    spec = BuilderSpec.model_validate(current.builder_spec)
                except Exception:
                    spec = None
        out[k.kpi_id] = spec
    return out


def _kpi_meta_lookup(db: Session, kpi_ids: set[int]) -> dict[int, tuple[str, str, dict, bool]]:
    """Bulk-fetch KPI name/chart-type/full-chart-config/active flag.

    Returns: ``{kpi_id: (name, chart_type, chart_config_dict, is_active)}``.
    The full config is what dashboards render with — without it cards
    would fall back to the executor's chart_picker auto-suggestion and
    silently override whatever the author chose in the editor.
    """
    if not kpi_ids:
        return {}
    rows = (
        db.query(KpiDefinition)
        .options(selectinload(KpiDefinition.versions))
        .filter(KpiDefinition.kpi_id.in_(kpi_ids))
        .all()
    )
    out: dict[int, tuple[str, str, dict, bool]] = {}
    for k in rows:
        chart_type = "table"
        chart_cfg: dict = {"type": "table", "config": {}}
        if k.current_version_id and k.versions:
            current = next(
                (v for v in k.versions if v.version_id == k.current_version_id),
                None,
            )
            if current and isinstance(current.chart_config, dict):
                chart_type = current.chart_config.get("type", "table") or "table"
                chart_cfg = current.chart_config
        out[k.kpi_id] = (k.name, chart_type, chart_cfg, k.is_active)
    return out


def _chart_config_payload(cfg: dict) -> ChartConfig:
    """Normalize a stored chart_config dict (which may be missing keys
    on legacy rows) into the response shape."""
    return ChartConfig(
        type=cfg.get("type", "table") or "table",
        config=cfg.get("config", {}) or {},
        style=cfg.get("style", {}) or {},
    )


# Phase D — Power BI–style 24-column grid (refined from the original
# 12-col so drag/resize jumps in finer increments — every cell is
# half the original width, every row is half the original height).
# Each unit of grid_h is one 40px row on the frontend; default
# grid_h = 8 gives a 320px tile, matching the legacy flex tile size.
_SIZE_TO_W = {"sm": 6, "md": 12, "lg": 18, "wide": 24}
_GRID_COLS = 24
_DEFAULT_H = 8


def _grid_coords_for(item) -> tuple[int, int, int, int]:
    """Return ``(x, y, w, h)`` for an item, backfilling from
    ``position`` + ``size_class`` when the persisted grid_* values are
    NULL (rows that predate the migration)."""
    if (item.grid_x is not None and item.grid_y is not None
            and item.grid_w is not None and item.grid_h is not None):
        return (
            int(item.grid_x), int(item.grid_y),
            int(item.grid_w), int(item.grid_h),
        )
    # Pack tiles linearly by ``position``: each tile claims its
    # size_class width on the current row; when a row would overflow
    # 12 cols, wrap to a new row. Reproduces what the legacy flex-grid
    # rendered, just expressed in grid coords.
    w = _SIZE_TO_W.get(item.size_class or "md", 6)
    h = _DEFAULT_H
    # Without sibling info this helper is per-item; the caller
    # (``_pack_layout``) re-runs it across all items to assign x/y.
    return (0, 0, w, h)


def _pack_layout(items) -> dict[int, tuple[int, int, int, int]]:
    """Greedy pack a list of dashboard items into 12-col rows ordered
    by ``position``, used to backfill missing grid_* coordinates so the
    first render matches the old flex layout. Items that already have
    explicit grid coords keep them — this only fills gaps."""
    out: dict[int, tuple[int, int, int, int]] = {}
    cursor_x = 0
    cursor_y = 0
    row_max_h = 0
    ordered = sorted(items, key=lambda i: (i.position, i.item_id))
    for it in ordered:
        if (it.grid_x is not None and it.grid_y is not None
                and it.grid_w is not None and it.grid_h is not None):
            out[it.item_id] = (int(it.grid_x), int(it.grid_y),
                               int(it.grid_w), int(it.grid_h))
            continue
        w = _SIZE_TO_W.get(it.size_class or "md", 6)
        h = _DEFAULT_H
        if cursor_x + w > _GRID_COLS:
            cursor_x = 0
            cursor_y += row_max_h or h
            row_max_h = 0
        out[it.item_id] = (cursor_x, cursor_y, w, h)
        cursor_x += w
        row_max_h = max(row_max_h, h)
    return out


def _to_detail(d: KpiDashboard, kpi_meta: dict[int, tuple[str, str, dict, bool]]) -> DashboardDetail:
    items: list[DashboardItemPayload] = []
    layout = _pack_layout(d.items)
    for it in d.items:
        meta = kpi_meta.get(it.kpi_id)
        if meta:
            kpi_name, chart_type, chart_cfg, is_active = meta
        else:
            kpi_name, chart_type, chart_cfg, is_active = (
                f"<deleted #{it.kpi_id}>", "table", {"type": "table", "config": {}}, False,
            )
        gx, gy, gw, gh = layout[it.item_id]
        items.append(DashboardItemPayload(
            item_id=it.item_id,
            kpi_id=it.kpi_id,
            kpi_name=kpi_name,
            kpi_chart_type=chart_type,
            kpi_chart_config=_chart_config_payload(chart_cfg),
            kpi_is_active=is_active,
            position=it.position,
            size_class=it.size_class,
            grid_x=gx,
            grid_y=gy,
            grid_w=gw,
            grid_h=gh,
            title_override=it.title_override,
            icon=it.icon,
            animation_in=it.animation_in,
            animation_out=it.animation_out,
            x_label=it.x_label,
            y_label=it.y_label,
            extra_filters=_filters_from_json(it.filters_json),
        ))
    return DashboardDetail(
        dashboard_id=d.dashboard_id,
        name=d.name,
        description=d.description,
        scope=d.scope,
        owner_user_id=d.owner_user_id,
        company_id=d.company_id,
        is_active=d.is_active,
        created_at=d.created_at,
        updated_at=d.updated_at,
        items=items,
    )


def _load_dashboard(db: Session, dashboard_id: int) -> KpiDashboard:
    d = (
        db.query(KpiDashboard)
        # Both items and assignments are eager-loaded so ``_can_view`` and
        # ``_to_detail`` can read them without firing N+1 queries.
        .options(
            selectinload(KpiDashboard.items),
            selectinload(KpiDashboard.assignments),
        )
        .filter(KpiDashboard.dashboard_id == dashboard_id)
        .first()
    )
    if d is None or not d.is_active:
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    return d


def _to_decoration_item(p: "dashboard_decorator.ItemPlacement") -> DashboardDecorationItem:
    return DashboardDecorationItem(
        item_id=p.item_id,
        grid_x=p.grid_x,
        grid_y=p.grid_y,
        grid_w=p.grid_w,
        grid_h=p.grid_h,
        size_class=p.size_class,
        title_override=p.title_override,
        icon=p.icon,
        animation_in=p.animation_in,
        animation_out=p.animation_out,
        x_label=p.x_label,
        y_label=p.y_label,
        extra_filters=list(p.extra_filters or []),
    )


def _to_assignment_info(a: KpiDashboardAssignment) -> DashboardAssignmentInfo:
    return DashboardAssignmentInfo(
        assignment_id=a.assignment_id,
        dashboard_id=a.dashboard_id,
        role_id=a.role_id,
        user_id=a.user_id,
        granted_by=a.granted_by,
        granted_at=a.granted_at,
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "",
        response_model=DashboardListResponse,
        dependencies=[Depends(perm("kpi:view"))],
    )
    def list_dashboards(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
        include_inactive: bool = Query(default=False),
        scope: Optional[str] = Query(default=None, description="Filter by scope: user|company"),
        search: Optional[str] = Query(default=None, max_length=200),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> DashboardListResponse:
        base = db.query(KpiDashboard)
        base = _scope_query(base, user)
        if not include_inactive:
            # ``== True`` (not ``.is_(True)``) — SQL Server rejects ``IS 1``.
            base = base.filter(KpiDashboard.is_active == True)  # noqa: E712
        if scope:
            base = base.filter(KpiDashboard.scope == scope)
        if search:
            base = base.filter(KpiDashboard.name.ilike(f"%{search}%"))

        total = base.with_entities(func.count(KpiDashboard.dashboard_id)).scalar() or 0

        # Pull dashboards + their item counts in one trip; selectinload would
        # also work but the count is cheaper than instantiating items.
        dashboards = (
            base.order_by(desc(KpiDashboard.updated_at))
            .limit(limit).offset(offset).all()
        )
        ids = [d.dashboard_id for d in dashboards]
        counts = {}
        if ids:
            for did, c in (
                db.query(KpiDashboardItem.dashboard_id, func.count(KpiDashboardItem.item_id))
                .filter(KpiDashboardItem.dashboard_id.in_(ids))
                .group_by(KpiDashboardItem.dashboard_id)
                .all()
            ):
                counts[did] = int(c)

        return DashboardListResponse(
            items=[_to_summary(d, counts.get(d.dashboard_id, 0)) for d in dashboards],
            total=int(total),
        )

    @router.post(
        "",
        response_model=DashboardDetail,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def create_dashboard(
        payload: DashboardCreate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardDetail:
        scope = _validate_scope(payload.scope)
        uid = _user_id(user)
        cid = _company_id(user)

        d = KpiDashboard(
            name=payload.name.strip(),
            description=payload.description or None,
            scope=scope,
            owner_user_id=uid,
            company_id=cid,
            is_active=True,
            created_by=uid,
            updated_by=uid,
        )
        db.add(d)
        db.commit()
        db.refresh(d)

        d = _load_dashboard(db, d.dashboard_id)
        return _to_detail(d, kpi_meta={})

    @router.get(
        "/{dashboard_id}",
        response_model=DashboardDetail,
        dependencies=[Depends(perm("kpi:view"))],
    )
    def get_dashboard(
        dashboard_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardDetail:
        d = _load_dashboard(db, dashboard_id)
        if not _can_view(d, user):
            # 404, not 403 — don't leak existence.
            raise HTTPException(status_code=404, detail="Dashboard not found.")
        kpi_ids = {it.kpi_id for it in d.items}
        return _to_detail(d, _kpi_meta_lookup(db, kpi_ids))

    @router.put(
        "/{dashboard_id}",
        response_model=DashboardDetail,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def update_dashboard(
        dashboard_id: int,
        payload: DashboardUpdate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardDetail:
        d = _load_dashboard(db, dashboard_id)
        if not _can_edit(d, user):
            raise HTTPException(status_code=403, detail="Cannot edit this dashboard.")

        if payload.name is not None:
            d.name = payload.name.strip()
        if payload.description is not None:
            d.description = payload.description or None
        if payload.scope is not None:
            d.scope = _validate_scope(payload.scope)
        d.updated_by = _user_id(user)

        db.commit()
        d = _load_dashboard(db, dashboard_id)
        kpi_ids = {it.kpi_id for it in d.items}
        return _to_detail(d, _kpi_meta_lookup(db, kpi_ids))

    @router.delete(
        "/{dashboard_id}",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def delete_dashboard(
        dashboard_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        d = _load_dashboard(db, dashboard_id)
        if not _can_delete(d, user):
            raise HTTPException(status_code=403, detail="Only the owner can delete this dashboard.")
        d.is_active = False
        d.updated_by = _user_id(user)
        db.commit()
        return {"deleted": True, "dashboard_id": dashboard_id}

    # ---- Items -----------------------------------------------------------

    @router.post(
        "/{dashboard_id}/items",
        response_model=DashboardItemPayload,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def add_item(
        dashboard_id: int,
        payload: DashboardItemCreate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardItemPayload:
        d = _load_dashboard(db, dashboard_id)
        if not _can_edit(d, user):
            raise HTTPException(status_code=403, detail="Cannot edit this dashboard.")

        size = _validate_size(payload.size_class)

        # Verify the KPI exists and the caller can see it. SuperAdmin sees
        # everything; otherwise the KPI's company must match the caller's
        # (matches the visibility rule in api/kpis.py).
        kpi = db.query(KpiDefinition).filter(KpiDefinition.kpi_id == payload.kpi_id).first()
        if kpi is None or not kpi.is_active:
            raise HTTPException(status_code=404, detail="KPI not found.")
        if not _is_super_admin(user) and kpi.company_id != _company_id(user):
            raise HTTPException(status_code=404, detail="KPI not found.")

        # Append at end of current ordering.
        next_pos = (
            db.query(func.coalesce(func.max(KpiDashboardItem.position), -1) + 1)
            .filter(KpiDashboardItem.dashboard_id == dashboard_id)
            .scalar()
        )

        item = KpiDashboardItem(
            dashboard_id=dashboard_id,
            kpi_id=payload.kpi_id,
            position=int(next_pos or 0),
            size_class=size,
            title_override=payload.title_override,
            created_by=_user_id(user),
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        meta = _kpi_meta_lookup(db, {kpi.kpi_id})
        kpi_name, chart_type, chart_cfg, is_active = meta.get(
            kpi.kpi_id,
            (kpi.name, "table", {"type": "table", "config": {}}, kpi.is_active),
        )
        # Pack the new item against the dashboard's existing layout so
        # it lands on a sensible empty slot rather than (0,0) on top of
        # everything else. Re-fetch all items to compute coords.
        d_after = _load_dashboard(db, dashboard_id)
        gx, gy, gw, gh = _pack_layout(d_after.items)[item.item_id]
        return DashboardItemPayload(
            item_id=item.item_id,
            kpi_id=item.kpi_id,
            kpi_name=kpi_name,
            kpi_chart_type=chart_type,
            kpi_chart_config=_chart_config_payload(chart_cfg),
            kpi_is_active=is_active,
            position=item.position,
            size_class=item.size_class,
            grid_x=gx, grid_y=gy, grid_w=gw, grid_h=gh,
            title_override=item.title_override,
            icon=item.icon,
            animation_in=item.animation_in,
            animation_out=item.animation_out,
            x_label=item.x_label,
            y_label=item.y_label,
            extra_filters=_filters_from_json(item.filters_json),
        )

    @router.put(
        "/{dashboard_id}/items/{item_id}",
        response_model=DashboardItemPayload,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def update_item(
        dashboard_id: int,
        item_id: int,
        payload: DashboardItemUpdate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardItemPayload:
        d = _load_dashboard(db, dashboard_id)
        if not _can_edit(d, user):
            raise HTTPException(status_code=403, detail="Cannot edit this dashboard.")

        item = (
            db.query(KpiDashboardItem)
            .filter(
                KpiDashboardItem.item_id == item_id,
                KpiDashboardItem.dashboard_id == dashboard_id,
            )
            .first()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found.")

        if payload.size_class is not None:
            item.size_class = _validate_size(payload.size_class)
        if payload.title_override is not None:
            item.title_override = payload.title_override or None
        if payload.icon is not None:
            item.icon = payload.icon or None
        if payload.animation_in is not None:
            v = _validate_animation(payload.animation_in)
            item.animation_in = v or None
        if payload.animation_out is not None:
            v = _validate_animation(payload.animation_out)
            item.animation_out = v or None
        if payload.x_label is not None:
            item.x_label = payload.x_label.strip() or None
        if payload.y_label is not None:
            item.y_label = payload.y_label.strip() or None
        if payload.extra_filters is not None:
            item.filters_json = _filters_to_json(payload.extra_filters) or None

        db.commit()
        db.refresh(item)

        meta = _kpi_meta_lookup(db, {item.kpi_id})
        kpi_name, chart_type, chart_cfg, is_active = meta.get(
            item.kpi_id,
            ("<missing>", "table", {"type": "table", "config": {}}, False),
        )
        d_after = _load_dashboard(db, dashboard_id)
        gx, gy, gw, gh = _pack_layout(d_after.items)[item.item_id]
        return DashboardItemPayload(
            item_id=item.item_id,
            kpi_id=item.kpi_id,
            kpi_name=kpi_name,
            kpi_chart_type=chart_type,
            kpi_chart_config=_chart_config_payload(chart_cfg),
            kpi_is_active=is_active,
            position=item.position,
            size_class=item.size_class,
            grid_x=gx, grid_y=gy, grid_w=gw, grid_h=gh,
            title_override=item.title_override,
            icon=item.icon,
            animation_in=item.animation_in,
            animation_out=item.animation_out,
            x_label=item.x_label,
            y_label=item.y_label,
            extra_filters=_filters_from_json(item.filters_json),
        )

    @router.delete(
        "/{dashboard_id}/items/{item_id}",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def delete_item(
        dashboard_id: int,
        item_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        d = _load_dashboard(db, dashboard_id)
        if not _can_edit(d, user):
            raise HTTPException(status_code=403, detail="Cannot edit this dashboard.")

        item = (
            db.query(KpiDashboardItem)
            .filter(
                KpiDashboardItem.item_id == item_id,
                KpiDashboardItem.dashboard_id == dashboard_id,
            )
            .first()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found.")

        db.delete(item)
        db.commit()
        return {"deleted": True, "item_id": item_id}

    @router.put(
        "/{dashboard_id}/layout",
        response_model=DashboardDetail,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def update_layout(
        dashboard_id: int,
        payload: DashboardLayoutRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardDetail:
        """Bulk update item positions + sizes — what the drag-drop end of
        a drop sends. Validates every item belongs to this dashboard before
        writing anything (no partial updates)."""
        d = _load_dashboard(db, dashboard_id)
        if not _can_edit(d, user):
            raise HTTPException(status_code=403, detail="Cannot edit this dashboard.")

        items_by_id = {it.item_id: it for it in d.items}
        for entry in payload.items:
            if entry.item_id not in items_by_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item {entry.item_id} does not belong to this dashboard.",
                )
            if entry.size_class is not None:
                _validate_size(entry.size_class)

        for entry in payload.items:
            it = items_by_id[entry.item_id]
            it.position = entry.position
            if entry.size_class is not None:
                it.size_class = entry.size_class
            # Phase D — persist grid coords when supplied (the
            # angular-gridster2 path). Each is independent so a partial
            # update is allowed; the read-time backfill fills any gaps.
            if entry.grid_x is not None:
                it.grid_x = entry.grid_x
            if entry.grid_y is not None:
                it.grid_y = entry.grid_y
            if entry.grid_w is not None:
                it.grid_w = entry.grid_w
            if entry.grid_h is not None:
                it.grid_h = entry.grid_h
            # Phase J.2 — AI Polish bundles per-card style + filter
            # changes into the same layout PUT. None = leave unchanged;
            # empty string clears icon/animation; empty list clears filters.
            if entry.title_override is not None:
                it.title_override = entry.title_override or None
            if entry.icon is not None:
                it.icon = entry.icon or None
            if entry.animation_in is not None:
                v = _validate_animation(entry.animation_in)
                it.animation_in = v or None
            if entry.animation_out is not None:
                v = _validate_animation(entry.animation_out)
                it.animation_out = v or None
            if entry.x_label is not None:
                it.x_label = entry.x_label.strip() or None
            if entry.y_label is not None:
                it.y_label = entry.y_label.strip() or None
            if entry.extra_filters is not None:
                it.filters_json = _filters_to_json(entry.extra_filters) or None

        d.updated_by = _user_id(user)
        db.commit()

        d = _load_dashboard(db, dashboard_id)
        kpi_ids = {it.kpi_id for it in d.items}
        return _to_detail(d, _kpi_meta_lookup(db, kpi_ids))

    # ---- Auto-decorate (Phase J.2) --------------------------------------

    @router.post(
        "/{dashboard_id}/auto-decorate",
        response_model=DashboardDecorateResponse,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def auto_decorate(
        dashboard_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardDecorateResponse:
        """AI proposes a tidier layout for the dashboard. Does NOT
        save — caller applies it through the existing /layout endpoint
        if the user accepts.

        Falls back to a rule-based packer when no LLM is configured
        or the model errors out, so the button always returns
        something useful.
        """
        d = _load_dashboard(db, dashboard_id)
        if not _can_edit(d, user):
            raise HTTPException(
                status_code=403,
                detail="Cannot edit this dashboard.",
            )

        # Pull KPI metadata so we know each item's chart_type — that's
        # what the decorator's heuristics are keyed on.
        kpi_meta = _kpi_meta_lookup(db, {it.kpi_id for it in d.items})
        # Also pull each KPI's BuilderSpec so the LLM can propose
        # filters against real columns. Raw-SQL KPIs return None and
        # the decorator silently skips filter proposals for them.
        builder_specs = _kpi_builder_specs(db, {it.kpi_id for it in d.items})
        layout = _pack_layout(d.items)

        views: list[dashboard_decorator.DashboardItemView] = []
        for it in d.items:
            meta = kpi_meta.get(it.kpi_id)
            chart_type = (meta[1] if meta else "table") or "table"
            kpi_name = (meta[0] if meta else f"#{it.kpi_id}") or f"#{it.kpi_id}"
            gx, gy, gw, gh = layout[it.item_id]
            views.append(dashboard_decorator.DashboardItemView(
                item_id=it.item_id,
                kpi_id=it.kpi_id,
                kpi_name=kpi_name,
                chart_type=chart_type,
                grid_x=gx, grid_y=gy, grid_w=gw, grid_h=gh,
                size_class=it.size_class or "md",
                title_override=it.title_override,
                icon=it.icon,
                animation_in=it.animation_in,
                animation_out=it.animation_out,
                x_label=it.x_label,
                y_label=it.y_label,
                extra_filters=_filters_from_json(it.filters_json),
                builder_spec=builder_specs.get(it.kpi_id),
            ))

        if not views:
            return DashboardDecorateResponse(items=[])

        cfg = deps.get_config()
        eff = settings_service.get_effective(db, env=os.environ)
        provider = eff.provider or cfg.llm_provider

        if provider is None:
            # No LLM — return the rule-based pack so the button still
            # does something useful (the user clicked Auto-decorate
            # for a reason).
            placements = dashboard_decorator._fallback_pack(views)
            return DashboardDecorateResponse(
                items=[_to_decoration_item(p) for p in placements],
                used_fallback=True,
                error="llm_disabled",
            )

        try:
            result = dashboard_decorator.decorate_dashboard(
                provider=provider,
                items=views,
                dashboard_name=d.name,
                max_tokens=eff.max_tokens_per_call,
            )
        except LlmProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        return DashboardDecorateResponse(
            items=[_to_decoration_item(p) for p in result.items],
            tokens=result.tokens,
            latency_ms=result.latency_ms,
            model=result.model,
            error=result.error,
            used_fallback=result.used_fallback,
        )

    # ---- Assignments (Phase A4) -----------------------------------------

    @router.get(
        "/{dashboard_id}/assignments",
        response_model=list[DashboardAssignmentInfo],
        dependencies=[Depends(perm("kpi:view"))],
    )
    def list_assignments(
        dashboard_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> list[DashboardAssignmentInfo]:
        d = _load_dashboard(db, dashboard_id)
        # The assignment list is itself sensitive — expose it only to
        # those who can manage it. Everyone else (incl. assignees who can
        # view the dashboard) gets a 403 here.
        if not _can_manage_assignments(d, user):
            raise HTTPException(
                status_code=403,
                detail="Only the owner or a SuperAdmin can view assignments.",
            )
        return [_to_assignment_info(a) for a in (d.assignments or [])]

    @router.post(
        "/{dashboard_id}/assignments",
        response_model=DashboardAssignmentInfo,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def add_assignment(
        dashboard_id: int,
        payload: DashboardAssignmentCreate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> DashboardAssignmentInfo:
        d = _load_dashboard(db, dashboard_id)
        if not _can_manage_assignments(d, user):
            raise HTTPException(
                status_code=403,
                detail="Only the owner or a SuperAdmin can grant assignments.",
            )

        # De-dupe — same (dashboard, role) or (dashboard, user) pair
        # should not be granted twice. Return the existing row rather
        # than creating a duplicate.
        existing_q = db.query(KpiDashboardAssignment).filter(
            KpiDashboardAssignment.dashboard_id == dashboard_id,
        )
        if payload.role_id is not None:
            existing = existing_q.filter(
                KpiDashboardAssignment.role_id == payload.role_id,
            ).first()
        else:
            existing = existing_q.filter(
                KpiDashboardAssignment.user_id == payload.user_id,
            ).first()
        if existing:
            return _to_assignment_info(existing)

        row = KpiDashboardAssignment(
            dashboard_id=dashboard_id,
            role_id=payload.role_id,
            user_id=payload.user_id,
            granted_by=_user_id(user),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _to_assignment_info(row)

    @router.delete(
        "/{dashboard_id}/assignments/{assignment_id}",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def revoke_assignment(
        dashboard_id: int,
        assignment_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        d = _load_dashboard(db, dashboard_id)
        if not _can_manage_assignments(d, user):
            raise HTTPException(
                status_code=403,
                detail="Only the owner or a SuperAdmin can revoke assignments.",
            )

        row = (
            db.query(KpiDashboardAssignment)
            .filter(
                KpiDashboardAssignment.assignment_id == assignment_id,
                KpiDashboardAssignment.dashboard_id == dashboard_id,
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Assignment not found.")

        db.delete(row)
        db.commit()
        return {"deleted": True, "assignment_id": assignment_id}

    return router
