"""Eval harness API (T-001).

Endpoints (all gated to ``kpi:settings`` — SuperAdmin only; eval cases
contain hand-crafted SQL and the runner exposes provider-level
behaviour, neither of which a regular user should mutate):

  GET    /eval/cases                  list active eval cases
  POST   /eval/cases                  create a case
  GET    /eval/cases/{id}             one case
  PUT    /eval/cases/{id}             update / soft-delete a case
  DELETE /eval/cases/{id}             hard-delete a case (rare)

  GET    /eval/runs                   recent runs (newest first)
  GET    /eval/runs/{id}              one run with per-case results
  POST   /eval/runs                   fire a new run synchronously

This mirrors the manual ``python -m kpi_studio.eval run`` flow so the
admin UI ("KPI Studio → Eval") can drive it without shell access.
Runs are synchronous today; once T-003 (scheduler) lands, the POST
will queue an async job instead.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import (
    KpiEvalCase, KpiEvalCaseResult, KpiEvalRun,
)
from kpi_studio.schemas import (
    EvalCaseCreate, EvalCaseListResponse, EvalCasePayload,
    EvalCaseResultPayload, EvalCaseUpdate,
    EvalRunListResponse, EvalRunPayload, EvalRunRequest,
)


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _case_to_payload(row: KpiEvalCase) -> EvalCasePayload:
    return EvalCasePayload(
        case_id=row.case_id,
        name=row.name,
        prompt=row.prompt,
        expected_tables=row.expected_tables,
        expected_columns=row.expected_columns,
        expected_row_count_min=row.expected_row_count_min,
        expected_row_count_max=row.expected_row_count_max,
        golden_sql=row.golden_sql,
        strict_tables=row.strict_tables,
        tags=row.tags,
        is_active=row.is_active,
        last_pass_at=row.last_pass_at.isoformat() if row.last_pass_at else None,
        last_fail_reason=row.last_fail_reason,
        pinned_snapshot_id=row.pinned_snapshot_id,
    )


def _result_to_payload(row: KpiEvalCaseResult) -> EvalCaseResultPayload:
    return EvalCaseResultPayload(
        result_id=row.result_id,
        case_id=row.case_id,
        status=row.status,
        produced_sql=row.produced_sql,
        produced_row_count=row.produced_row_count,
        tables_referenced=row.tables_referenced,
        columns_referenced=row.columns_referenced,
        failure_reasons=row.failure_reasons,
        failure_detail=row.failure_detail,
        duration_ms=row.duration_ms,
        tokens_used=row.tokens_used,
        nl_run_id=row.nl_run_id,
    )


def _run_to_payload(row: KpiEvalRun, *, include_results: bool = False,
                    db: Optional[Session] = None) -> EvalRunPayload:
    pass_rate = (row.cases_passed / row.cases_total) if row.cases_total else 0.0
    results = None
    if include_results and db is not None:
        rows = (
            db.query(KpiEvalCaseResult)
            .filter(KpiEvalCaseResult.eval_run_id == row.eval_run_id)
            .order_by(KpiEvalCaseResult.result_id.asc())
            .all()
        )
        results = [_result_to_payload(r) for r in rows]
    return EvalRunPayload(
        eval_run_id=row.eval_run_id,
        started_at=row.started_at.isoformat(),
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        triggered_by=row.triggered_by,
        tags_filter=row.tags_filter,
        snapshot_id=row.snapshot_id,
        prompt_version=row.prompt_version,
        cases_total=row.cases_total,
        cases_passed=row.cases_passed,
        cases_failed=row.cases_failed,
        cases_errored=row.cases_errored,
        cases_skipped=row.cases_skipped,
        pass_rate=pass_rate,
        summary_json=row.summary_json,
        results=results,
    )


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    # --- Cases CRUD ---------------------------------------------------------

    @router.get(
        "/cases",
        response_model=EvalCaseListResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def list_cases(
        include_inactive: bool = Query(False),
        tag: Optional[str] = Query(None, description="Filter by single tag."),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        q = db.query(KpiEvalCase)
        if not include_inactive:
            q = q.filter(KpiEvalCase.is_active == True)  # noqa: E712
        rows = q.order_by(KpiEvalCase.case_id.asc()).all()
        if tag:
            rows = [r for r in rows if r.tags and tag in r.tags]
        return EvalCaseListResponse(
            items=[_case_to_payload(r) for r in rows],
            total=len(rows),
        )

    @router.post(
        "/cases",
        response_model=EvalCasePayload,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def create_case(
        payload: EvalCaseCreate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ):
        row = KpiEvalCase(
            name=payload.name,
            prompt=payload.prompt,
            expected_tables=payload.expected_tables,
            expected_columns=payload.expected_columns,
            expected_row_count_min=payload.expected_row_count_min,
            expected_row_count_max=payload.expected_row_count_max,
            golden_sql=payload.golden_sql,
            strict_tables=payload.strict_tables,
            tags=payload.tags,
            pinned_snapshot_id=payload.pinned_snapshot_id,
            created_by=_user_id(user),
            updated_by=_user_id(user),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _case_to_payload(row)

    @router.get(
        "/cases/{case_id}",
        response_model=EvalCasePayload,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def get_case(case_id: int, db: Session = Depends(db_dep), _user: Any = Depends(auth)):
        row = db.get(KpiEvalCase, case_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        return _case_to_payload(row)

    @router.put(
        "/cases/{case_id}",
        response_model=EvalCasePayload,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def update_case(
        case_id: int,
        payload: EvalCaseUpdate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ):
        row = db.get(KpiEvalCase, case_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")

        # Apply every field the caller actually sent — Pydantic's
        # exclude_unset keeps untouched fields at their stored value
        # rather than overwriting with the dataclass default.
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value)
        row.updated_by = _user_id(user)
        db.commit()
        db.refresh(row)
        return _case_to_payload(row)

    @router.delete(
        "/cases/{case_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def delete_case(case_id: int, db: Session = Depends(db_dep), _user: Any = Depends(auth)):
        """Hard-delete a case. The runner respects ``is_active=false`` —
        prefer ``PUT /eval/cases/{id}`` with ``is_active=false`` to keep
        history. Hard delete is provided for accidental-insert cleanup."""
        row = db.get(KpiEvalCase, case_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
        db.delete(row)
        db.commit()
        return None

    # --- Runs ---------------------------------------------------------------

    @router.get(
        "/runs",
        response_model=EvalRunListResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def list_runs(
        limit: int = Query(50, ge=1, le=500),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        rows = (
            db.query(KpiEvalRun)
            .order_by(KpiEvalRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return EvalRunListResponse(
            items=[_run_to_payload(r) for r in rows],
            total=len(rows),
        )

    @router.get(
        "/runs/{run_id}",
        response_model=EvalRunPayload,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def get_run(run_id: int, db: Session = Depends(db_dep), _user: Any = Depends(auth)):
        row = db.get(KpiEvalRun, run_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
        return _run_to_payload(row, include_results=True, db=db)

    @router.post(
        "/runs",
        response_model=EvalRunPayload,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def trigger_run(
        payload: EvalRunRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ):
        """Fire an eval run synchronously and return the full run +
        results. Today this blocks the request until every case
        completes — fine while case-count is small (under 100). Once
        T-003 (scheduler) ships, this becomes a background-queue
        enqueue with a polling endpoint."""
        cfg = deps.get_config()
        if cfg is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "KPI Studio config not bound — internal startup error.",
            )
        from kpi_studio.eval.runner import run_eval
        summary = run_eval(
            db=db,
            config=cfg,
            tags=payload.tags,
            case_ids=payload.case_ids,
            triggered_by="api",
            triggered_by_user_id=_user_id(user),
            against_snapshot_id=payload.against_snapshot_id,
        )
        row = db.get(KpiEvalRun, summary.eval_run_id)
        return _run_to_payload(row, include_results=True, db=db)

    return router
