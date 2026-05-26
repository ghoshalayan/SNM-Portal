"""Call-log admin API (observability, shipped 2026-05-25).

Read-only endpoints over ``kpi_llm_call_log``. Authoring lives in
``OpenAICompatibleProvider._post`` via ``call_logger.record``; this
module is just the projection.

Routes (mounted at ``/api/v1/kpi/settings/call-logs``):

  GET    /                            list (with filters)
  GET    /{id}                        one row (full body)
  GET    /correlation/{correlation_id} every call sharing one correlation
                                       (= every LLM call from one user op)
  DELETE /                            purge all (admin debug — careful)

All endpoints SuperAdmin-only.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import CALL_LOG_SOURCES, KpiLlmCallLog
from kpi_studio.schemas import (
    CallLogCorrelationResponse, CallLogDetail,
    CallLogListResponse, CallLogSummary,
)


def _summary(row: KpiLlmCallLog) -> CallLogSummary:
    return CallLogSummary(
        call_log_id=row.call_log_id,
        correlation_id=row.correlation_id,
        trigger_source=row.trigger_source,
        trigger_ref_kind=row.trigger_ref_kind,
        trigger_ref_id=row.trigger_ref_id,
        user_id=row.user_id,
        provider_config_id=row.provider_config_id,
        provider_kind=row.provider_kind,
        provider_label=row.provider_label,
        base_url=row.base_url,
        model=row.model,
        stage_key=row.stage_key,
        response_status=row.response_status,
        succeeded=row.succeeded,
        error=row.error,
        latency_ms=row.latency_ms,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        started_at=row.started_at.isoformat(),
    )


def _detail(row: KpiLlmCallLog) -> CallLogDetail:
    base = _summary(row).model_dump()
    return CallLogDetail(
        **base,
        request_method=row.request_method,
        request_path=row.request_path,
        request_body=row.request_body,
        request_headers=row.request_headers,
        request_truncated=row.request_truncated,
        response_body=row.response_body,
        response_truncated=row.response_truncated,
    )


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "",
        response_model=CallLogListResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def list_call_logs(
        limit: int = Query(50, ge=1, le=500),
        cursor: Optional[int] = Query(None, description="Last call_log_id "
                                                          "from the previous page."),
        trigger_source: Optional[str] = Query(None),
        provider_config_id: Optional[int] = Query(None),
        ok: Optional[bool] = Query(None, description="True = only successes, False = only failures."),
        correlation_id: Optional[str] = Query(None),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        q = db.query(KpiLlmCallLog)
        if trigger_source:
            if trigger_source not in CALL_LOG_SOURCES:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    f"Unknown trigger_source: {trigger_source!r}")
            q = q.filter(KpiLlmCallLog.trigger_source == trigger_source)
        if provider_config_id is not None:
            q = q.filter(KpiLlmCallLog.provider_config_id == provider_config_id)
        if ok is not None:
            q = q.filter(KpiLlmCallLog.succeeded == ok)
        if correlation_id:
            q = q.filter(KpiLlmCallLog.correlation_id == correlation_id)
        if cursor is not None:
            q = q.filter(KpiLlmCallLog.call_log_id < cursor)

        rows = (
            q.order_by(desc(KpiLlmCallLog.call_log_id))
            .limit(limit + 1)  # +1 to detect next page
            .all()
        )
        next_cursor: Optional[int] = None
        if len(rows) > limit:
            next_cursor = rows[limit - 1].call_log_id
            rows = rows[:limit]
        return CallLogListResponse(
            items=[_summary(r) for r in rows],
            total=len(rows),
            next_cursor=next_cursor,
        )

    @router.get(
        "/{call_log_id}",
        response_model=CallLogDetail,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def get_call_log(
        call_log_id: int,
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        row = db.get(KpiLlmCallLog, call_log_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Call log not found")
        return _detail(row)

    @router.get(
        "/correlation/{correlation_id}",
        response_model=CallLogCorrelationResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def get_correlation(
        correlation_id: str,
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        rows = (
            db.query(KpiLlmCallLog)
            .filter(KpiLlmCallLog.correlation_id == correlation_id)
            .order_by(KpiLlmCallLog.call_log_id.asc())  # chronological
            .all()
        )
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "No calls with that correlation_id")
        return CallLogCorrelationResponse(
            correlation_id=correlation_id,
            items=[_detail(r) for r in rows],
        )

    @router.delete(
        "",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def purge_all(
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        """Purge every call-log row. Use with care — meant for the
        admin's "clean slate" button when the log is overwhelming."""
        db.query(KpiLlmCallLog).delete(synchronize_session=False)
        db.commit()
        return None

    return router
