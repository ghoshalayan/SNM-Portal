"""Central registration point for scheduled jobs (T-003).

This module is imported once during FastAPI startup (before
``scheduler.start_scheduler()``). Importing it has the side-effect of
calling ``scheduler.register(...)`` for every job we want APScheduler
to attach.

**Convention:** every future roadmap task that needs a scheduled job
adds its registration here (or in a sibling module imported from here).
Keeps the "what jobs exist" answer to a single grep.

Current registrations:

* ``scheduler_heartbeat`` — every 6 minutes, no-op + log. Proves the
  scheduler is alive end-to-end (visible in /api/v1/kpi/jobs admin
  page). First infrastructure job; future tasks add real work
  (T-204 anchor refresh, T-601 value indexer, T-701 schema-drift
  detector, T-707 data-shape drift).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from kpi_studio.services import call_logger, provider_healthcheck, scheduler

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heartbeat — the canonical "scheduler is alive" job. Cheap, audited,
# no business effect. Returns an integer (always 1) so the admin UI's
# ``items_processed`` column has a non-null value to render.
# ---------------------------------------------------------------------------

def _heartbeat(_db: Optional[Session] = None) -> int:
    log.info("kpi_studio.scheduler: heartbeat at %s",
             datetime.now(timezone.utc).isoformat())
    return 1


def _provider_healthcheck(db: Optional[Session] = None) -> int:
    """T-004: probe every stage's configured (provider, model) pair.

    Returns the number of probes that ran — surfaced in the admin UI
    as ``items_processed``. Drops sharply (or to 0) when a deploy
    misconfigures the LLM settings; that's the regression signal.

    2026-05-25: honours the ``healthcheck_auto_enabled`` admin toggle.
    When off, returns 0 immediately — no LLM cost. Items_processed of
    0 with status='success' is the "intentionally skipped" signal in
    the admin UI.
    """
    if db is None:
        log.warning("kpi_studio.scheduler: healthcheck skipped — no DB session")
        return 0

    # Cost gate — skip the upstream calls when the admin has disabled
    # automatic probes. Manual "Run health check" button still works.
    from kpi_studio.services import settings_service
    eff = settings_service.get_effective(db, env=None)
    if not eff.healthcheck_auto_enabled:
        log.info(
            "kpi_studio.scheduler: provider healthcheck skipped — "
            "healthcheck_auto_enabled=false",
        )
        return 0

    # force=True so the weekly run bypasses the in-process cache and
    # actually re-probes the upstream APIs.
    result = provider_healthcheck.run_healthcheck(db, force=True)
    if not result.overall_ok:
        log.warning(
            "kpi_studio.scheduler: provider healthcheck reported failures: %s",
            [f"{p.provider}/{p.model}: {p.error}" for p in result.probes if not p.ok],
        )
    return len(result.probes)


def _call_log_prune(db: Optional[Session] = None) -> int:
    """Daily cleanup: hard-delete kpi_llm_call_log rows older than the
    configured retention window. Returns the number of rows deleted —
    surfaced as ``items_processed`` in the admin UI."""
    if db is None:
        return 0
    from kpi_studio.services import settings_service
    eff = settings_service.get_effective(db, env=None)
    return call_logger.prune_older_than(db, days=eff.call_log_retention_days)


def register_all() -> None:
    """Call at startup before ``scheduler.start_scheduler()``.

    Idempotent — ``scheduler.register`` replaces by name, so re-imports
    (test code, reloaders) don't accumulate duplicates.
    """
    scheduler.register(
        name="scheduler_heartbeat",
        func=_heartbeat,
        interval_seconds=360,  # every 6 minutes
        description=(
            "Liveness probe — the scheduler is alive iff this row "
            "shows a recent success. No business effect."
        ),
    )
    scheduler.register(
        name="provider_healthcheck",
        func=_provider_healthcheck,
        # 7 days. Probes are cheap (~3-5 tokens each) but a deprecated
        # model needs to surface faster than that in practice — admins
        # can hit "Run now" from the admin UI any time.
        interval_seconds=7 * 24 * 60 * 60,
        description=(
            "T-004: probes every configured stage model with a 1-token "
            "completion. Surfaces deprecated models / rotated keys."
        ),
    )
    scheduler.register(
        name="call_log_prune",
        func=_call_log_prune,
        # Daily. Cheap query — delete by indexed timestamp range.
        interval_seconds=24 * 60 * 60,
        description=(
            "Delete kpi_llm_call_log rows older than "
            "settings.call_log_retention_days (default 7)."
        ),
    )


# Auto-register on import so callers just need ``from kpi_studio.services
# import scheduled_jobs  # noqa`` to get the side-effect.
register_all()
