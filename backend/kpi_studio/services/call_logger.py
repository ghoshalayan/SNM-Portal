"""LLM call-log observability (shipped 2026-05-25).

Records one row per outbound LLM HTTP call to ``kpi_llm_call_log``.
Used by ``OpenAICompatibleProvider._post`` to log every request/
response transparent to the caller.

The "correlation context" is the key design choice — every entry
point that triggers LLM work (chat turn, /nl/generate, eval case,
healthcheck pass) opens a ``log_context(...)`` block. Any LLM call
made within that block gets stamped with the same correlation_id,
trigger_source, and (optionally) trigger_ref_* / stage_key. That's
how the admin UI groups 12 individual probe + agent + insight calls
under one row that says "one chat turn".

Two reasons to use a contextvar rather than thread-locals:
  * Works under asyncio if/when the agent goes async.
  * Auto-restored on exception — no risk of leaking state across
    requests sharing a worker thread.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping, Optional

from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import CALL_LOG_SOURCES, KpiLlmCallLog


log = logging.getLogger(__name__)


# Cap per side. Anything larger is truncated + flagged. 64 KB is
# generous — typical chat request + response is < 16 KB — but small
# enough that 10k logs fit in ~1 GB.
DEFAULT_BODY_CAP_BYTES = 64 * 1024

# Override via env for environments that want larger / smaller caps.
BODY_CAP_BYTES = int(
    os.environ.get("KPI_CALL_LOG_BODY_CAP_BYTES") or DEFAULT_BODY_CAP_BYTES
)


@dataclass
class _Context:
    correlation_id: str
    trigger_source: str
    trigger_ref_kind: Optional[str] = None
    trigger_ref_id: Optional[int] = None
    user_id: Optional[int] = None
    company_id: Optional[int] = None
    stage_key: Optional[str] = None
    # Override per call — set inside an inner contextmanager to mark
    # "this specific call belongs to a different stage" without
    # rewriting the outer context.
    stage_overrides: dict = field(default_factory=dict)


_ctx: contextvars.ContextVar[Optional[_Context]] = contextvars.ContextVar(
    "kpi_call_log_ctx", default=None,
)


# ---------------------------------------------------------------------------
# Context-manager API
# ---------------------------------------------------------------------------

@contextmanager
def log_context(
    *,
    trigger_source: str,
    trigger_ref_kind: Optional[str] = None,
    trigger_ref_id: Optional[int] = None,
    user_id: Optional[int] = None,
    company_id: Optional[int] = None,
    stage_key: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Iterator[str]:
    """Open a logging context. Every LLM call made inside the with-block
    is stamped with the same correlation_id + trigger metadata.

    Pre-existing context is replaced (not nested) — the use case is
    "one user-facing operation = one correlation id"; nesting two
    operations is rare and would mean the log groups wrong.

    Yields the correlation_id so the caller can stash it on its own
    audit row (e.g. ``KpiNlRun.correlation_id`` — future addition).
    """
    if trigger_source not in CALL_LOG_SOURCES:
        # Don't reject — just log. Stamping "unknown" is more useful
        # than a 500 because a typo'd source.
        log.warning("kpi_studio.call_logger: unknown trigger_source=%r",
                    trigger_source)

    ctx = _Context(
        correlation_id=(correlation_id or uuid.uuid4().hex),
        trigger_source=trigger_source,
        trigger_ref_kind=trigger_ref_kind,
        trigger_ref_id=trigger_ref_id,
        user_id=user_id,
        company_id=company_id,
        stage_key=stage_key,
    )
    token = _ctx.set(ctx)
    try:
        yield ctx.correlation_id
    finally:
        _ctx.reset(token)


@contextmanager
def stage_scope(stage_key: str) -> Iterator[None]:
    """Inner scope to mark "this call belongs to stage X". Useful when
    one entry point fires multiple LLM calls for different stages
    (preflight, agent_default, insight_generator) within the same
    correlation context."""
    parent = _ctx.get()
    if parent is None:
        yield
        return
    saved = parent.stage_key
    parent.stage_key = stage_key
    try:
        yield
    finally:
        parent.stage_key = saved


def current_correlation_id() -> Optional[str]:
    ctx = _ctx.get()
    return ctx.correlation_id if ctx else None


# ---------------------------------------------------------------------------
# Recorder — called from OpenAICompatibleProvider._post
# ---------------------------------------------------------------------------

def record(
    *,
    provider_kind: str,
    provider_label: Optional[str],
    provider_config_id: Optional[int],
    base_url: str,
    model: str,
    request_method: str,
    request_path: str,
    request_body: Any,
    request_headers: Mapping[str, str],
    response_status: Optional[int],
    response_body: Optional[Any],
    succeeded: bool,
    error: Optional[str],
    latency_ms: int,
    started_at: Optional[datetime] = None,
) -> None:
    """Persist one call-log row. Best-effort — never raises.

    Reads the contextvar set by ``log_context`` for the correlation /
    trigger metadata. When no context is active (background job, etc.)
    the row goes in with ``trigger_source='unknown'`` and a null
    correlation — still queryable, just not grouped.
    """
    try:
        # Cost-toggle check. Reading the toggle is cheap — same
        # cached settings everything else uses.
        cfg = deps.get_config()
        if cfg is None:
            return  # module not bound (e.g. import-time test).
        if not _logging_enabled(cfg):
            return

        ctx = _ctx.get()

        # Serialise + truncate bodies.
        req_body_str, req_truncated = _truncate(_json_safe(request_body))
        if response_body is None:
            resp_body_str, resp_truncated = None, False
        else:
            resp_body_str, resp_truncated = _truncate(_json_safe(response_body))

        headers_str, _ = _truncate(_json_safe(_mask_headers(request_headers)))

        # Mine token usage from the response body (works for OpenAI-
        # compatible providers; quietly None when shape doesn't match).
        prompt_tok, completion_tok, total_tok = _extract_token_usage(response_body)

        row = KpiLlmCallLog(
            correlation_id=(ctx.correlation_id if ctx else None),
            trigger_source=(ctx.trigger_source if ctx else "unknown"),
            trigger_ref_kind=(ctx.trigger_ref_kind if ctx else None),
            trigger_ref_id=(ctx.trigger_ref_id if ctx else None),
            company_id=(ctx.company_id if ctx else None),
            user_id=(ctx.user_id if ctx else None),
            provider_config_id=provider_config_id,
            provider_kind=provider_kind,
            provider_label=provider_label,
            base_url=base_url,
            model=model,
            stage_key=(ctx.stage_key if ctx else None),
            request_method=request_method,
            request_path=request_path,
            request_body=req_body_str,
            request_headers=headers_str,
            request_truncated=req_truncated,
            response_status=response_status,
            response_body=resp_body_str,
            response_truncated=resp_truncated,
            succeeded=succeeded,
            error=(error[:8000] if error else None),
            latency_ms=int(latency_ms),
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
            total_tokens=total_tok,
            started_at=started_at or datetime.now(timezone.utc),
        )
        with cfg.metadata_session_factory() as session:
            session.add(row)
            session.commit()
    except Exception as exc:
        # NEVER raise out of the logger — the user-facing LLM call
        # must not fail because of an audit row insert failing.
        log.warning("kpi_studio.call_logger: record failed: %r", exc)


# ---------------------------------------------------------------------------
# Pruning (called from a scheduled job)
# ---------------------------------------------------------------------------

def prune_older_than(db: Session, *, days: int) -> int:
    """Hard-delete call-log rows older than ``days``. Returns rowcount.

    Used by the daily prune job registered in scheduled_jobs.py.
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    result = (
        db.query(KpiLlmCallLog)
        .filter(KpiLlmCallLog.started_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(result or 0)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _logging_enabled(cfg) -> bool:
    """DB row > env > default(True). Same resolution as healthcheck."""
    try:
        from kpi_studio.services import settings_service
        with cfg.metadata_session_factory() as session:
            eff = settings_service.get_effective(session, env=None)
            return bool(eff.call_logging_enabled)
    except Exception:
        # If settings_service blows up, default to logging-on rather
        # than silently going dark.
        return True


_REDACTED = "[REDACTED]"


def _mask_headers(headers: Mapping[str, str]) -> dict:
    """Mask credential headers before persist. Authorization +
    OpenRouter-specific HTTP-Referer / X-Title are kept (former
    masked, latter passed through as they're operational metadata,
    not secrets)."""
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        if not isinstance(k, str):
            continue
        kl = k.lower()
        if kl == "authorization":
            # Keep the scheme prefix ("Bearer", "Api-Key") so the
            # admin can see what was sent without exposing the token.
            v_str = str(v)
            scheme = v_str.split(" ", 1)[0] if " " in v_str else "Bearer"
            out[k] = f"{scheme} {_REDACTED}"
        elif kl in ("x-api-key", "api-key", "openai-api-key"):
            out[k] = _REDACTED
        else:
            out[k] = str(v)
    return out


def _json_safe(value: Any) -> str:
    """Render to a JSON string. When ``value`` isn't JSON-serialisable,
    fall back to ``repr`` wrapped in a JSON envelope so the column
    always stores a string (the UI's JSON parser can tell which side
    is which)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"_unserialisable_repr": repr(value)},
                          ensure_ascii=False)


def _truncate(text: str) -> tuple[str, bool]:
    """Cap to BODY_CAP_BYTES. Returns (text, truncated_flag)."""
    if not text:
        return text, False
    # Approximate by char length (UTF-8 multi-byte chars get under-
    # counted but the column is nvarchar so chars not bytes is the
    # right unit anyway).
    if len(text) <= BODY_CAP_BYTES:
        return text, False
    return text[:BODY_CAP_BYTES] + f"... [truncated, original {len(text)} chars]", True


def _extract_token_usage(
    response_body: Any,
) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Mine ``usage`` from an OpenAI-compatible response body.

    OpenAI / Cerebras / OpenRouter all return:
      {"usage": {"prompt_tokens": N, "completion_tokens": N, "total_tokens": N}}

    Returns (prompt, completion, total) with any missing field as None.
    """
    if not isinstance(response_body, dict):
        return None, None, None
    usage = response_body.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    p = usage.get("prompt_tokens")
    c = usage.get("completion_tokens")
    t = usage.get("total_tokens")
    return (
        int(p) if isinstance(p, (int, float)) else None,
        int(c) if isinstance(c, (int, float)) else None,
        int(t) if isinstance(t, (int, float)) else None,
    )
