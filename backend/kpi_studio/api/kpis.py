"""KPI CRUD + preview + run — Phase A1.

Endpoints:
  GET    /kpis                  list
  POST   /kpis                  create
  GET    /kpis/{id}             detail (with current version)
  PUT    /kpis/{id}             patch (creates a new version when query/chart change)
  DELETE /kpis/{id}             soft delete
  POST   /kpis/preview          run an unsaved query (also returns chart suggestion)
  POST   /kpis/{id}/run         re-execute the saved KPI live
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, selectinload

from kpi_studio import deps
from kpi_studio.models import KpiDefinition, KpiVersion
from kpi_studio.schemas import (
    BuilderSpec, ChartConfig, ChartSuggestion, ExecutionResultPayload,
    KpiCreateRequest, KpiDetail, KpiListResponse, KpiPreviewRequest,
    KpiRunRequest, KpiSummary, KpiUpdateRequest, KpiVersionSummary,
)
from kpi_studio.services import chart_picker, relationship_service
from kpi_studio.services.executor import (
    QueryExecutionError, execute_safe_query,
)
from kpi_studio.services.spec_compiler import SpecCompileError, compile_spec
from kpi_studio.services.sql_safety import SqlSafetyError
from kpi_studio.services.time_periods import (
    InvalidPeriodError, resolve_period,
)


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


def _scope_query(q, user: Any):
    """Limit a KpiDefinition query to rows the caller is allowed to see."""
    if _is_super_admin(user):
        return q
    cid = _company_id(user)
    if cid is None:
        return q.filter(False)  # no tenant → see nothing
    return q.filter(KpiDefinition.company_id == cid)


def _ensure_visible(kpi: KpiDefinition, user: Any) -> None:
    if _is_super_admin(user):
        return
    cid = _company_id(user)
    if kpi.company_id != cid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="KPI not found.")


def _execution_payload(
    db: Session,
    *,
    user: Any,
    sql: str,
    source: str,
    kpi_version_id: Optional[int] = None,
    period: Optional[str] = None,
    start_date: Any = None,
    end_date: Any = None,
) -> ExecutionResultPayload:
    cfg = deps.get_config()

    # Resolve period → (start, end) datetime pair and bind as
    # ``:start_date`` / ``:end_date``. We *always* bind both, falling back
    # to a very wide window when no period is selected — that way a KPI
    # whose SQL references the placeholders still works as "all time" by
    # default (SQLAlchemy errors if a referenced :name has no binding).
    # KPIs that don't use the placeholders just ignore the values.
    try:
        window = resolve_period(period, start_date=start_date, end_date=end_date)
    except InvalidPeriodError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_period",
            "message": str(exc),
        })
    if window is None:
        from datetime import datetime as _dt, timezone as _tz
        ws = _dt(1900, 1, 1, tzinfo=_tz.utc)
        we = _dt(2999, 12, 31, tzinfo=_tz.utc)
    else:
        ws, we = window
    # Phase I — auto-bind tenant + user context on every run so a
    # single KPI definition can serve every user with their own data
    # slice (e.g. ``WHERE company_id = :company_id`` or
    # ``WHERE owner_user_id = :user_id``). KPIs that don't reference
    # these binds simply ignore the extra values.
    bind_params: dict = {
        "start_date": ws,
        "end_date": we,
        "company_id": _company_id(user),
        "user_id": _user_id(user),
    }

    try:
        result = execute_safe_query(
            cfg.target_engine,
            db,
            sql=sql,
            source=source,
            user_id=_user_id(user),
            company_id=_company_id(user),
            kpi_version_id=kpi_version_id,
            bind_params=bind_params,
        )
    except SqlSafetyError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "validation_failed",
            "message": str(exc),
            "findings": getattr(exc, "findings", []),
        })
    except QueryExecutionError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "execution_failed",
            "message": str(exc),
        })

    suggestion = chart_picker.suggest_chart(result.columns, result.rows)
    return ExecutionResultPayload(
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
        duration_ms=result.duration_ms,
        rewritten_sql=result.rewritten_sql,
        notes=result.notes,
        suggestion=ChartSuggestion(
            type=suggestion.type,
            config=suggestion.config,
            reason=suggestion.reason,
            alternates=suggestion.alternates,
        ),
    )


def _to_summary(kpi: KpiDefinition) -> KpiSummary:
    chart_type = "table"
    if kpi.current_version_id and kpi.versions:
        current = next((v for v in kpi.versions if v.version_id == kpi.current_version_id), None)
        if current and isinstance(current.chart_config, dict):
            chart_type = current.chart_config.get("type", "table") or "table"
    return KpiSummary(
        kpi_id=kpi.kpi_id,
        name=kpi.name,
        description=kpi.description,
        chart_type=chart_type,
        current_version_id=kpi.current_version_id,
        owner_user_id=kpi.owner_user_id,
        company_id=kpi.company_id,
        is_active=kpi.is_active,
        updated_at=kpi.updated_at,
    )


def _to_detail(kpi: KpiDefinition) -> KpiDetail:
    current = None
    if kpi.current_version_id:
        current = next((v for v in kpi.versions if v.version_id == kpi.current_version_id), None)
    chart_cfg = None
    query_text = None
    db_key = "primary"
    time_column = None
    builder_spec = None
    if current:
        cfg_dict = current.chart_config if isinstance(current.chart_config, dict) else {}
        chart_cfg = ChartConfig(
            type=cfg_dict.get("type", "table"),
            config=cfg_dict.get("config", {}),
        )
        query_text = current.query_text
        db_key = current.database_key or "primary"
        time_column = current.time_column
        # Re-hydrate the builder spec so the editor can drop the user
        # straight back into the wells UI without a round-trip.
        if isinstance(current.builder_spec, dict):
            try:
                builder_spec = BuilderSpec.model_validate(current.builder_spec)
            except Exception:
                # Defensive: a corrupted spec shouldn't break detail loading.
                builder_spec = None

    return KpiDetail(
        kpi_id=kpi.kpi_id,
        name=kpi.name,
        description=kpi.description,
        company_id=kpi.company_id,
        owner_user_id=kpi.owner_user_id,
        is_active=kpi.is_active,
        created_at=kpi.created_at,
        updated_at=kpi.updated_at,
        current_version_id=kpi.current_version_id,
        query_text=query_text,
        chart_config=chart_cfg,
        database_key=db_key,
        time_column=time_column,
        builder_spec=builder_spec,
        versions=[
            KpiVersionSummary(
                version_id=v.version_id,
                version_no=v.version_no,
                chart_type=(v.chart_config or {}).get("type", "table"),
                created_at=v.created_at,
                created_by=v.created_by,
            )
            for v in kpi.versions
        ],
    )


def _resolve_authoring(
    *,
    db: Session,
    user: Any,
    builder_spec: Optional[BuilderSpec],
    raw_query: Optional[str],
    raw_chart: Optional[ChartConfig],
) -> tuple[str, dict, Optional[dict]]:
    """Pick the source-of-truth for a save and produce the persisted
    triple ``(query_text, chart_config_dict, builder_spec_json_or_None)``.

    Builder mode wins when ``builder_spec`` is set — the compiler
    runs with the live relationship graph so cross-table BuilderFields
    auto-emit ``LEFT JOIN``s. Raw mode passes through unchanged.
    Caller still runs sql_safety on the resulting query_text (one
    validator, both paths).
    """
    if builder_spec is not None:
        rels = relationship_service.list_relationships(
            db, company_id=_company_id(user),
        )
        try:
            compiled = compile_spec(builder_spec, relationships=rels)
        except SpecCompileError as exc:
            raise HTTPException(status_code=400, detail={
                "error": "builder_compile_failed",
                "message": str(exc),
            })
        return (
            compiled.sql,
            compiled.chart_config.model_dump(),
            builder_spec.model_dump(by_alias=True),
        )
    if not raw_query or raw_chart is None:
        raise HTTPException(status_code=400, detail={
            "error": "missing_payload",
            "message": "Provide either builder_spec or query_text + chart_config.",
        })
    return raw_query, raw_chart.model_dump(), None


# ---------------------------------------------------------------------------
# Route handlers (registered inside build_router so Depends() captures the
# already-bound host auth dep — module-level decorators would freeze the
# placeholder).
# ---------------------------------------------------------------------------

def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "",
        response_model=KpiListResponse,
        dependencies=[Depends(perm("kpi:view"))],
    )
    def list_kpis(
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
        include_inactive: bool = Query(default=False),
        search: Optional[str] = Query(default=None, max_length=200),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> KpiListResponse:
        base = db.query(KpiDefinition).options(selectinload(KpiDefinition.versions))
        base = _scope_query(base, user)
        if not include_inactive:
            # ``== True`` (not ``.is_(True)``) — SQL Server rejects ``IS 1``.
            base = base.filter(KpiDefinition.is_active == True)  # noqa: E712
        if search:
            like = f"%{search}%"
            base = base.filter(KpiDefinition.name.ilike(like))

        total = base.with_entities(func.count(KpiDefinition.kpi_id)).scalar() or 0
        items = (
            base.order_by(desc(KpiDefinition.updated_at))
            .limit(limit).offset(offset).all()
        )
        return KpiListResponse(items=[_to_summary(k) for k in items], total=int(total))

    @router.get(
        "/{kpi_id}",
        response_model=KpiDetail,
        dependencies=[Depends(perm("kpi:view"))],
    )
    def get_kpi(
        kpi_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> KpiDetail:
        kpi = (
            db.query(KpiDefinition)
            .options(selectinload(KpiDefinition.versions))
            .filter(KpiDefinition.kpi_id == kpi_id)
            .first()
        )
        if kpi is None:
            raise HTTPException(status_code=404, detail="KPI not found.")
        _ensure_visible(kpi, user)
        return _to_detail(kpi)

    @router.post(
        "",
        response_model=KpiDetail,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def create_kpi(
        payload: KpiCreateRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> KpiDetail:
        # Builder spec (if present) compiles to SQL + chart_config and
        # replaces any raw fields the caller sent. The same validator
        # then runs over the resulting SQL — one safety pass for both
        # authoring modes.
        query_text, chart_dict, spec_dict = _resolve_authoring(
            db=db, user=user,
            builder_spec=payload.builder_spec,
            raw_query=payload.query_text,
            raw_chart=payload.chart_config,
        )
        try:
            from kpi_studio.services.sql_safety import validate_select_query
            validate_select_query(query_text)
        except SqlSafetyError as exc:
            raise HTTPException(status_code=400, detail={
                "error": "validation_failed",
                "message": str(exc),
                "findings": getattr(exc, "findings", []),
            })

        uid = _user_id(user)
        cid = _company_id(user)

        kpi = KpiDefinition(
            name=payload.name.strip(),
            description=(payload.description or None),
            company_id=cid,
            owner_user_id=uid,
            is_active=True,
            created_by=uid,
            updated_by=uid,
        )
        db.add(kpi)
        db.flush()

        version = KpiVersion(
            kpi_id=kpi.kpi_id,
            version_no=1,
            query_text=query_text,
            database_key=payload.database_key,
            chart_config=chart_dict,
            time_column=payload.time_column,
            builder_spec=spec_dict,
            created_by=uid,
        )
        db.add(version)
        db.flush()

        kpi.current_version_id = version.version_id
        db.commit()
        db.refresh(kpi)

        kpi = (
            db.query(KpiDefinition)
            .options(selectinload(KpiDefinition.versions))
            .filter(KpiDefinition.kpi_id == kpi.kpi_id)
            .first()
        )
        return _to_detail(kpi)  # type: ignore[arg-type]

    @router.put(
        "/{kpi_id}",
        response_model=KpiDetail,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def update_kpi(
        kpi_id: int,
        payload: KpiUpdateRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> KpiDetail:
        kpi = (
            db.query(KpiDefinition)
            .options(selectinload(KpiDefinition.versions))
            .filter(KpiDefinition.kpi_id == kpi_id)
            .first()
        )
        if kpi is None or not kpi.is_active:
            raise HTTPException(status_code=404, detail="KPI not found.")
        _ensure_visible(kpi, user)

        uid = _user_id(user)
        if payload.name is not None:
            kpi.name = payload.name.strip()
        if payload.description is not None:
            kpi.description = payload.description or None
        kpi.updated_by = uid

        # Roll a new version when any version-scoped field changes —
        # query / chart / database / time_column / builder_spec are all
        # part of the immutable snapshot a dashboard pins to.
        version_changed = (
            payload.query_text is not None
            or payload.chart_config is not None
            or payload.database_key is not None
            or payload.time_column is not None
            or payload.builder_spec is not None
        )
        if version_changed:
            current = next(
                (v for v in kpi.versions if v.version_id == kpi.current_version_id),
                None,
            )

            # Resolve authoring source-of-truth. When the patch carries a
            # ``builder_spec`` (or the existing version was builder-mode and
            # the caller didn't switch to raw), compile it and use the
            # output. Otherwise fall back to raw-SQL fields, mixing the
            # patch with the prior version where the caller didn't touch
            # a field — same merge semantics as legacy raw-SQL updates.
            if payload.builder_spec is not None:
                # Explicit builder-mode update.
                new_query, new_chart, new_spec = _resolve_authoring(
                    db=db, user=user,
                    builder_spec=payload.builder_spec,
                    raw_query=None, raw_chart=None,
                )
            elif (
                payload.query_text is None
                and payload.chart_config is None
                and current is not None
                and isinstance(current.builder_spec, dict)
            ):
                # No raw fields touched, current is builder-mode → keep
                # the existing spec; the patch is for time_column /
                # database_key / name / description only.
                new_query = current.query_text
                new_chart = current.chart_config or {"type": "table", "config": {}}
                new_spec = current.builder_spec
            else:
                # Raw-SQL update path. ``new_spec=None`` means a builder
                # KPI converted to raw becomes raw permanently (one-way,
                # by design — round-trip from raw → spec is the hard
                # direction we deliberately don't support).
                new_query = payload.query_text or (current.query_text if current else "")
                new_chart = (
                    payload.chart_config.model_dump()
                    if payload.chart_config is not None
                    else (current.chart_config if current else {"type": "table", "config": {}})
                )
                new_spec = None

            try:
                from kpi_studio.services.sql_safety import validate_select_query
                validate_select_query(new_query)
            except SqlSafetyError as exc:
                raise HTTPException(status_code=400, detail={
                    "error": "validation_failed",
                    "message": str(exc),
                    "findings": getattr(exc, "findings", []),
                })

            new_db = payload.database_key or (current.database_key if current else "primary")
            # ``time_column`` is treated as an explicit overwrite — sending
            # an empty string clears the filter binding.
            new_time_column = (
                payload.time_column
                if payload.time_column is not None
                else (current.time_column if current else None)
            )
            new_version_no = (max((v.version_no for v in kpi.versions), default=0) + 1)

            version = KpiVersion(
                kpi_id=kpi.kpi_id,
                version_no=new_version_no,
                query_text=new_query,
                database_key=new_db,
                chart_config=new_chart,
                time_column=new_time_column,
                builder_spec=new_spec,
                created_by=uid,
            )
            db.add(version)
            db.flush()
            kpi.current_version_id = version.version_id

        db.commit()

        kpi = (
            db.query(KpiDefinition)
            .options(selectinload(KpiDefinition.versions))
            .filter(KpiDefinition.kpi_id == kpi_id)
            .first()
        )
        return _to_detail(kpi)  # type: ignore[arg-type]

    @router.delete(
        "/{kpi_id}",
        dependencies=[Depends(perm("kpi:author"))],
    )
    def delete_kpi(
        kpi_id: int,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> dict:
        kpi = db.query(KpiDefinition).filter(KpiDefinition.kpi_id == kpi_id).first()
        if kpi is None or not kpi.is_active:
            raise HTTPException(status_code=404, detail="KPI not found.")
        _ensure_visible(kpi, user)

        kpi.is_active = False
        kpi.updated_by = _user_id(user)
        db.commit()
        return {"deleted": True, "kpi_id": kpi_id}

    @router.post(
        "/preview",
        response_model=ExecutionResultPayload,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def preview_query(
        payload: KpiPreviewRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> ExecutionResultPayload:
        # Builder mode: compile spec → SQL on the fly so the live preview
        # in the wells editor mirrors the eventual save. Compilation
        # errors surface as 400 with a builder_compile_failed code.
        if payload.builder_spec is not None:
            rels = relationship_service.list_relationships(
                db, company_id=_company_id(user),
            )
            try:
                compiled = compile_spec(payload.builder_spec, relationships=rels)
            except SpecCompileError as exc:
                raise HTTPException(status_code=400, detail={
                    "error": "builder_compile_failed",
                    "message": str(exc),
                })
            sql = compiled.sql
        else:
            sql = payload.query_text or ""
        return _execution_payload(
            db,
            user=user,
            sql=sql,
            source="preview",
            period=payload.period,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )

    @router.post(
        "/{kpi_id}/run",
        response_model=ExecutionResultPayload,
        dependencies=[Depends(perm("kpi:view"))],
    )
    def run_kpi(
        kpi_id: int,
        # Body is optional — empty body still works as a period-less run.
        # FastAPI treats ``KpiRunRequest`` with all-Optional fields as accepting
        # an empty JSON body or even no body at all.
        body: Optional[KpiRunRequest] = None,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> ExecutionResultPayload:
        kpi = (
            db.query(KpiDefinition)
            .options(selectinload(KpiDefinition.versions))
            .filter(KpiDefinition.kpi_id == kpi_id)
            .first()
        )
        if kpi is None or not kpi.is_active or not kpi.current_version_id:
            raise HTTPException(status_code=404, detail="KPI not found.")
        _ensure_visible(kpi, user)

        current = next((v for v in kpi.versions if v.version_id == kpi.current_version_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="KPI has no current version.")

        # Phase J.2 — when the caller (a dashboard card) sends extra_filters,
        # recompile from the saved BuilderSpec with the extras merged into
        # the WHERE clause. Raw-SQL KPIs have no spec to recompile, so the
        # extras are silently ignored (rather than failing — the safer
        # default for legacy KPIs that pre-date the builder).
        sql = current.query_text
        extras = (body.extra_filters if body else None) or []
        if extras and isinstance(current.builder_spec, dict):
            try:
                spec = BuilderSpec.model_validate(current.builder_spec)
            except Exception:
                spec = None
            if spec is not None:
                merged = list(spec.filters or []) + list(extras)
                spec = spec.model_copy(update={"filters": merged})
                rels = relationship_service.list_relationships(
                    db, company_id=_company_id(user),
                )
                try:
                    compiled = compile_spec(spec, relationships=rels)
                    sql = compiled.sql
                except SpecCompileError as exc:
                    raise HTTPException(status_code=400, detail={
                        "error": "extra_filter_compile_failed",
                        "message": str(exc),
                    })

        return _execution_payload(
            db,
            user=user,
            sql=sql,
            source="kpi_run",
            kpi_version_id=current.version_id,
            period=body.period if body else None,
            start_date=body.start_date if body else None,
            end_date=body.end_date if body else None,
        )

    return router
