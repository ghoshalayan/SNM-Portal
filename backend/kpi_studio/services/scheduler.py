"""KPI Studio in-process scheduler (T-003).

One ``BackgroundScheduler`` runs alongside the FastAPI worker. Jobs are
declared in-code via :func:`register` — the registry is the source of
truth for "what jobs exist", and the actual ``BackgroundScheduler`` is
just the dispatcher. Every job execution is wrapped so:

* A ``KpiScheduledJobRun`` row is inserted before the job starts.
* The wrapper catches every exception → records ``status='failed'``
  and the trimmed error.
* Wall-clock duration + ``items_processed`` (when the job returns it)
  are stamped on the row at the end.

Why in-process: per the project's design constraint, KPI Studio adds
no external broker (no Celery, no Redis). For multi-worker deployments
the BackgroundScheduler should run in only one worker — gated by the
``KPI_SCHEDULER_ENABLED`` env var so the other workers skip
``start_scheduler``. The same env var also disables the scheduler
entirely in tests.

Public surface:

* :func:`register`            — declare a job at import-time.
* :func:`start_scheduler`     — call from FastAPI startup.
* :func:`shutdown_scheduler`  — call from FastAPI shutdown.
* :func:`list_jobs`           — admin API enumerates registered jobs.
* :func:`run_now`             — admin API triggers a one-off execution.
* :func:`list_recent_runs`    — admin API drills into per-job history.

Jobs that need a database session should accept ``db: Session`` as their
sole parameter; the wrapper opens a session and closes it. Jobs that
need to write back ``items_processed`` should return an int.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session, sessionmaker

from kpi_studio import deps
from kpi_studio.models import KpiScheduledJobRun

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job descriptor
# ---------------------------------------------------------------------------

@dataclass
class JobSpec:
    """Everything needed to run one scheduled job.

    ``func`` may accept zero or one positional argument; when it takes
    one, the wrapper passes a fresh ``Session``. ``func``'s return
    value (when truthy and int-like) is recorded as
    ``items_processed``; anything else is ignored.

    Trigger is either an APScheduler trigger object (``IntervalTrigger`` /
    ``CronTrigger``) or one of the convenience strings the runtime
    parses below.
    """
    name: str
    func: Callable[..., Any]
    trigger: Any
    description: str = ""
    enabled: bool = True
    # Per-job env override: ``KPI_JOB_<NAME_UPPER>_ENABLED=false`` disables
    # without a code change. Useful for noisy / heavy jobs in dev.
    env_disable_key: Optional[str] = None


# Public registry. Modules call ``register(...)`` at import time;
# ``start_scheduler`` attaches each enabled job to APScheduler.
_REGISTRY: dict[str, JobSpec] = {}
_REGISTRY_LOCK = Lock()
_SCHEDULER: Optional[BackgroundScheduler] = None
_SESSION_FACTORY: Optional[sessionmaker] = None


# ---------------------------------------------------------------------------
# Public API — registration
# ---------------------------------------------------------------------------

def register(
    *,
    name: str,
    func: Callable[..., Any],
    interval_seconds: Optional[int] = None,
    cron: Optional[str] = None,
    description: str = "",
    enabled: bool = True,
) -> JobSpec:
    """Register a job. Idempotent — re-registering the same name
    replaces the prior spec (useful for hot-reload during dev).

    Exactly one of ``interval_seconds`` / ``cron`` must be supplied:

      * ``interval_seconds=900``  — every 15 minutes from start time.
      * ``cron="0 2 * * *"``      — at 02:00 every day (cron 5-field).

    The ``env_disable_key`` convention auto-derives from ``name``:
    ``KPI_JOB_<UPPER_NAME>_ENABLED``; setting that var to ``false``
    keeps the job declared (visible in the admin UI) but skipped at
    scheduler start.
    """
    if (interval_seconds is None) == (cron is None):
        raise ValueError(
            f"job {name!r} must supply exactly one of interval_seconds / cron"
        )
    if interval_seconds is not None:
        trigger: Any = IntervalTrigger(seconds=interval_seconds)
    else:
        trigger = CronTrigger.from_crontab(cron)  # type: ignore[arg-type]

    spec = JobSpec(
        name=name,
        func=func,
        trigger=trigger,
        description=description,
        enabled=enabled,
        env_disable_key=f"KPI_JOB_{name.upper().replace('-', '_')}_ENABLED",
    )
    with _REGISTRY_LOCK:
        _REGISTRY[name] = spec
    log.info("kpi_studio.scheduler: registered %s", name)
    return spec


def list_jobs() -> list[JobSpec]:
    """Snapshot of every registered job, in stable name order."""
    with _REGISTRY_LOCK:
        return sorted(_REGISTRY.values(), key=lambda j: j.name)


def get_job(name: str) -> Optional[JobSpec]:
    with _REGISTRY_LOCK:
        return _REGISTRY.get(name)


# ---------------------------------------------------------------------------
# Public API — lifecycle
# ---------------------------------------------------------------------------

def start_scheduler() -> Optional[BackgroundScheduler]:
    """Start APScheduler with every enabled job attached.

    Returns the live scheduler instance (for tests) or ``None`` when
    the scheduler is disabled via env. Idempotent — repeated calls are
    no-ops.
    """
    global _SCHEDULER, _SESSION_FACTORY

    if _SCHEDULER is not None:
        return _SCHEDULER

    if not _scheduler_enabled():
        log.info("kpi_studio.scheduler: disabled via KPI_SCHEDULER_ENABLED")
        return None

    cfg = deps.get_config()
    if cfg is None:
        log.warning(
            "kpi_studio.scheduler: deps.get_config() returned None — "
            "scheduler will start without DB session factory; DB-touching "
            "jobs will skip themselves."
        )
    else:
        _SESSION_FACTORY = cfg.metadata_session_factory

    sched = BackgroundScheduler()
    for spec in list_jobs():
        if not spec.enabled:
            log.info("kpi_studio.scheduler: skipping %s (enabled=False)", spec.name)
            continue
        if not _job_env_enabled(spec):
            log.info("kpi_studio.scheduler: skipping %s (%s=false)",
                     spec.name, spec.env_disable_key)
            continue
        sched.add_job(
            _wrap_job(spec),
            trigger=spec.trigger,
            id=spec.name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )
    sched.start()
    _SCHEDULER = sched
    log.info("kpi_studio.scheduler: started with %d job(s)",
             len([j for j in list_jobs() if j.enabled]))
    return sched


def shutdown_scheduler() -> None:
    """Stop the scheduler gracefully. Called from FastAPI shutdown."""
    global _SCHEDULER
    if _SCHEDULER is None:
        return
    try:
        _SCHEDULER.shutdown(wait=False)
    except Exception as exc:
        log.warning("kpi_studio.scheduler: shutdown raised %s", exc)
    _SCHEDULER = None


# ---------------------------------------------------------------------------
# Public API — manual trigger + run history
# ---------------------------------------------------------------------------

def run_now(name: str, *, triggered_by_user_id: Optional[int] = None) -> int:
    """Fire one job synchronously (admin "Run now" affordance).

    Runs in the calling thread — fine for short jobs (index refresh,
    drift detection). For long jobs we can later add a queue, but the
    initial use cases (10s–60s of work) don't warrant it. Returns the
    ``run_id`` of the audit row.
    """
    spec = get_job(name)
    if spec is None:
        raise KeyError(f"unknown job: {name!r}")
    return _execute(spec, trigger_source="api_trigger",
                    triggered_by_user_id=triggered_by_user_id)


def list_recent_runs(*, name: Optional[str] = None, limit: int = 50) -> list[KpiScheduledJobRun]:
    """Read recent run rows. Optional ``name`` filter scopes to one job."""
    if _SESSION_FACTORY is None:
        return []
    with _SESSION_FACTORY() as session:
        q = session.query(KpiScheduledJobRun)
        if name:
            q = q.filter(KpiScheduledJobRun.job_name == name)
        rows = (
            q.order_by(KpiScheduledJobRun.started_at.desc())
            .limit(limit)
            .all()
        )
        # Detach so the caller can use them outside the session.
        for r in rows:
            session.expunge(r)
        return rows


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _wrap_job(spec: JobSpec) -> Callable[[], None]:
    """Return a no-arg closure APScheduler can call. Captures ``spec``."""
    def _wrapped() -> None:
        _execute(spec, trigger_source="scheduled")
    return _wrapped


def _execute(spec: JobSpec, *, trigger_source: str,
             triggered_by_user_id: Optional[int] = None) -> int:
    """Run one job + insert the audit row. Returns the ``run_id``.

    Failures are caught and recorded but never re-raised — APScheduler
    must keep the schedule alive even when one job dies repeatedly.
    """
    session = _SESSION_FACTORY() if _SESSION_FACTORY else None
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)

    # Insert the ``running`` row up-front so a crashed worker leaves a
    # detectable artifact ("running" rows older than X = missed
    # heartbeats), not silence.
    run_row = KpiScheduledJobRun(
        job_name=spec.name,
        trigger_source=trigger_source,
        triggered_by_user_id=triggered_by_user_id,
        started_at=started_at,
        status="running",
    )
    # Capture the assigned PK as soon as it's known so we can return it
    # after the session closes. Reading ``run_row.run_id`` *after*
    # ``session.close()`` triggers a lazy reload from the detached
    # instance — that's the DetachedInstanceError we used to crash with.
    run_id_local: int = 0
    if session is not None:
        try:
            session.add(run_row)
            session.commit()
            session.refresh(run_row)
            run_id_local = int(run_row.run_id or 0)
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

    items_processed: Optional[int] = None
    status = "success"
    error: Optional[str] = None

    try:
        # The job may take ``db`` or no args. Sniff by calling with the
        # session first and falling back if the signature rejects it.
        # Inspect-based dispatch would be more robust but adds import
        # weight; the two-form contract is simple and explicit.
        try:
            result = spec.func(session) if session is not None else spec.func()
        except TypeError as exc:
            if "positional argument" in str(exc) or "argument" in str(exc):
                result = spec.func()
            else:
                raise

        if isinstance(result, int):
            items_processed = result
    except Exception as exc:
        status = "failed"
        error = repr(exc)[:2000]
        log.exception("kpi_studio.scheduler: job %s failed", spec.name)
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        if session is not None and run_id_local:
            try:
                run_row.status = status
                run_row.error = error
                run_row.items_processed = items_processed
                run_row.duration_ms = duration_ms
                run_row.finished_at = datetime.now(timezone.utc)
                session.commit()
            except Exception:
                try:
                    session.rollback()
                except Exception:
                    pass
            finally:
                session.close()

    # ``run_id_local`` was captured pre-close, so this never touches a
    # detached instance.
    return run_id_local


def _scheduler_enabled() -> bool:
    v = (os.environ.get("KPI_SCHEDULER_ENABLED") or "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def _job_env_enabled(spec: JobSpec) -> bool:
    if not spec.env_disable_key:
        return True
    v = os.environ.get(spec.env_disable_key)
    if v is None:
        return True
    return v.strip().lower() not in ("0", "false", "no", "off")
