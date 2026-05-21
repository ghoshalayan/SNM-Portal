"""Background task scaffold for the SNM Portal backend (Phase 0).

Wraps FastAPI's built-in ``BackgroundTasks`` with structured logging so
fire-and-forget operations (email send, future SMS/WhatsApp, audit log
fan-out, etc.) don't block API request threads and surface failures in
the application log instead of going silent.

Scope decision (Phase 0):
  * Use FastAPI's in-process ``BackgroundTasks`` — runs after the
    response is flushed, in the same worker. No new infrastructure.
  * Durable / retriable queue (Celery + Redis, RQ, etc.) is deferred
    until Phase 4 notifications, when "must survive worker restart"
    becomes a real requirement.

Public API:
  * ``run_in_background(tasks, fn, *args, **kwargs)`` — register a
    coroutine/callable to run after response. Wraps the callable in a
    try/except that logs structured success/failure events.
  * ``submit_email(tasks, smtp_config, to_email, subject, html_body, **kw)``
    — convenience for the most common case.

Usage from a FastAPI route handler:
    @router.post("/foo")
    def foo(..., bg: BackgroundTasks):
        run_in_background(bg, do_work, arg1, arg2, kwarg=value)
        return {"status": "queued"}
"""
from __future__ import annotations

import time
from typing import Any, Callable

from fastapi import BackgroundTasks

from app.core.logging_config import get_logger

log = get_logger(__name__)


def run_in_background(
    tasks: BackgroundTasks,
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> None:
    """Register ``fn(*args, **kwargs)`` to run after the response is
    flushed. The callable is wrapped so any exception is caught and
    logged structurally (instead of getting swallowed by FastAPI's
    background-task error handling).

    The wrapper records a ``bg_task`` event with ``ok=True`` on success
    and ``ok=False`` + traceback on failure, plus the elapsed time so
    we can spot slow background work.
    """
    fn_name = getattr(fn, "__qualname__", getattr(fn, "__name__", repr(fn)))

    def _wrapped() -> None:
        started = time.monotonic()
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 — we deliberately catch all
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.exception(
                "bg_task failed",
                extra={"task": fn_name, "ok": False, "elapsed_ms": elapsed_ms},
            )
        else:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.info(
                "bg_task ok",
                extra={"task": fn_name, "ok": True, "elapsed_ms": elapsed_ms},
            )

    tasks.add_task(_wrapped)


def submit_email(
    tasks: BackgroundTasks,
    smtp_config: dict,
    to_email: str,
    subject: str,
    html_body: str,
    attachment: bytes | None = None,
    attachment_filename: str | None = None,
) -> None:
    """Queue an email send for after-response delivery. Failures land
    in the structured log only — the calling endpoint returns 202
    immediately, so the user sees "Queued" right away.

    For the original synchronous behaviour (caller wants HTTP 500 on
    SMTP failure), keep using ``email_service.send_email`` directly.
    """
    # Deferred import — keeps the background module free of the email
    # service's transitive ORM imports for unit tests.
    from app.services.email_service import email_service

    run_in_background(
        tasks,
        email_service.send_email,
        smtp_config=smtp_config,
        to_email=to_email,
        subject=subject,
        html_body=html_body,
        attachment=attachment,
        attachment_filename=attachment_filename,
    )
