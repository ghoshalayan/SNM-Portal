"""Scheduler admin API (T-003).

Three endpoints — all SuperAdmin-only (gated to ``kpi:settings``):

  GET    /jobs                       list registered jobs + last-run summary
  GET    /jobs/{name}/runs           recent runs for one job
  POST   /jobs/{name}/trigger        fire one job synchronously

Jobs are declared in code (services.scheduler.register), not via the
API — schedules are version-controlled, not user-mutable. The API is
strictly observability + manual trigger.
"""
from __future__ import annotations

from typing import Any, Optional

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import KpiScheduledJobRun
from kpi_studio.schemas import (
    JobTriggerInfo,
    ScheduledJobListResponse,
    ScheduledJobPayload,
    ScheduledJobRunListResponse,
    ScheduledJobRunPayload,
    ScheduledJobTriggerResponse,
)
from kpi_studio.services import scheduler as scheduler_svc


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _trigger_info(spec, sched_job) -> JobTriggerInfo:
    """Flatten an APScheduler trigger + the (optional) attached job
    into the wire shape the admin UI renders."""
    t = spec.trigger
    info = JobTriggerInfo(kind="unknown")
    if isinstance(t, IntervalTrigger):
        info.kind = "interval"
        # APScheduler stores interval as a timedelta on the trigger.
        info.interval_seconds = int(t.interval.total_seconds())
    elif isinstance(t, CronTrigger):
        info.kind = "cron"
        # cron's internal representation isn't a 5-field string; reconstruct
        # a readable expression from the fields.
        try:
            info.cron_expression = " ".join(str(f) for f in t.fields)
        except Exception:
            info.cron_expression = repr(t)
    if sched_job is not None and getattr(sched_job, "next_run_time", None):
        info.next_fire_at = sched_job.next_run_time.isoformat()
    return info


def _last_run_for(db: Session, job_name: str) -> Optional[KpiScheduledJobRun]:
    return (
        db.query(KpiScheduledJobRun)
        .filter(KpiScheduledJobRun.job_name == job_name)
        .order_by(KpiScheduledJobRun.started_at.desc())
        .first()
    )


def _run_to_payload(row: KpiScheduledJobRun) -> ScheduledJobRunPayload:
    return ScheduledJobRunPayload(
        run_id=row.run_id,
        job_name=row.job_name,
        trigger_source=row.trigger_source,
        triggered_by_user_id=row.triggered_by_user_id,
        status=row.status,
        error=row.error,
        items_processed=row.items_processed,
        duration_ms=row.duration_ms,
        started_at=row.started_at.isoformat(),
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
        detail_json=row.detail_json,
    )


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "",
        response_model=ScheduledJobListResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def list_jobs(
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ) -> ScheduledJobListResponse:
        specs = scheduler_svc.list_jobs()
        sched = scheduler_svc._SCHEDULER  # noqa: SLF001 — intentional admin reach-in
        items: list[ScheduledJobPayload] = []
        for spec in specs:
            sched_job = sched.get_job(spec.name) if sched is not None else None
            last = _last_run_for(db, spec.name)
            items.append(ScheduledJobPayload(
                name=spec.name,
                description=spec.description,
                enabled=spec.enabled,
                trigger=_trigger_info(spec, sched_job),
                last_run_id=last.run_id if last else None,
                last_run_status=last.status if last else None,
                last_run_started_at=last.started_at.isoformat() if last else None,
                last_run_finished_at=(last.finished_at.isoformat()
                                      if last and last.finished_at else None),
                last_run_duration_ms=last.duration_ms if last else None,
            ))
        return ScheduledJobListResponse(
            items=items,
            total=len(items),
            scheduler_active=sched is not None,
        )

    @router.get(
        "/{name}/runs",
        response_model=ScheduledJobRunListResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def list_runs(
        name: str,
        limit: int = Query(50, ge=1, le=500),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ) -> ScheduledJobRunListResponse:
        if scheduler_svc.get_job(name) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown job: {name}")
        rows = (
            db.query(KpiScheduledJobRun)
            .filter(KpiScheduledJobRun.job_name == name)
            .order_by(KpiScheduledJobRun.started_at.desc())
            .limit(limit)
            .all()
        )
        return ScheduledJobRunListResponse(
            items=[_run_to_payload(r) for r in rows],
            total=len(rows),
        )

    @router.post(
        "/{name}/trigger",
        response_model=ScheduledJobTriggerResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def trigger_job(
        name: str,
        _db: Session = Depends(db_dep),  # held so the dep graph is consistent
        user: Any = Depends(auth),
    ) -> ScheduledJobTriggerResponse:
        if scheduler_svc.get_job(name) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown job: {name}")
        try:
            run_id = scheduler_svc.run_now(name, triggered_by_user_id=_user_id(user))
        except Exception as exc:
            # Job raised inside scheduler — already audited as ``failed``;
            # surface a 200 with the run row's status so the UI can show
            # the row in red rather than swallowing the trigger silently.
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                f"Job execution raised: {exc!r}",
            )
        # Re-read the row to get the final status (success / failed).
        from kpi_studio.deps import get_config
        cfg = get_config()
        if cfg is not None:
            with cfg.metadata_session_factory() as session:
                row = session.get(KpiScheduledJobRun, run_id)
                return ScheduledJobTriggerResponse(
                    run_id=run_id,
                    job_name=name,
                    status=row.status if row else "unknown",
                )
        return ScheduledJobTriggerResponse(run_id=run_id, job_name=name, status="unknown")

    return router
