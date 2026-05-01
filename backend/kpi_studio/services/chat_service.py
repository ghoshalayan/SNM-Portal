"""Chat service — sessions, messages, and the turn pipeline.

Phase B1 reuses the existing A7 NL→SQL agent to drive each turn:

  user prompt
    → ``run_agent`` (tool-use loop with iteration + token caps)
    → if SQL proposed: ``execute_safe_query``
    → store user + assistant message rows
    → return both for the frontend timeline

Insight generation (B3) and rolling-summary compaction land later. The
table schema already has the columns those phases need.
"""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable, Generator, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, selectinload

from kpi_studio.models import KpiChatMessage, KpiChatSession
from kpi_studio.providers.llm.base import LlmProvider
from kpi_studio.services import (
    chart_picker, chat_summarizer, insight_generator, introspector,
    nl2sql_agent, settings_service,
)
from kpi_studio.services.executor import (
    QueryExecutionError, execute_safe_query,
)

log = logging.getLogger(__name__)


_TITLE_MAX = 60


def _derive_title(prompt: str) -> str:
    """Use the first line of the first prompt, capped at TITLE_MAX,
    when the user didn't provide one."""
    line = (prompt or "").strip().splitlines()[0:1]
    text = (line[0] if line else "Untitled chat").strip()
    if len(text) > _TITLE_MAX:
        return text[:_TITLE_MAX - 1].rstrip() + "…"
    return text or "Untitled chat"


# ---------------------------------------------------------------------------
# Session lookup + visibility
# ---------------------------------------------------------------------------

def list_sessions(
    db: Session,
    *,
    user_id: Optional[int],
    include_inactive: bool = False,
    limit: int = 50,
) -> list[Tuple[KpiChatSession, int]]:
    """Return ``(session, message_count)`` pairs for the caller's
    sessions, newest-updated first. Per-user — no sharing in B1."""
    q = db.query(KpiChatSession).filter(KpiChatSession.user_id == user_id)
    if not include_inactive:
        q = q.filter(KpiChatSession.is_active == True)  # noqa: E712 — SQL Server compat
    sessions = q.order_by(desc(KpiChatSession.updated_at)).limit(limit).all()
    if not sessions:
        return []

    counts: dict[int, int] = {}
    for sid, c in (
        db.query(KpiChatMessage.chat_session_id, func.count(KpiChatMessage.chat_message_id))
        .filter(KpiChatMessage.chat_session_id.in_([s.chat_session_id for s in sessions]))
        .group_by(KpiChatMessage.chat_session_id)
        .all()
    ):
        counts[sid] = int(c)
    return [(s, counts.get(s.chat_session_id, 0)) for s in sessions]


def get_session(
    db: Session, session_id: int, *, user_id: Optional[int],
) -> Optional[KpiChatSession]:
    """Eager-load messages. Owner check enforced — returns ``None`` for
    sessions belonging to another user (which becomes a 404 at the API
    layer; we don't leak existence)."""
    sess = (
        db.query(KpiChatSession)
        .options(selectinload(KpiChatSession.messages))
        .filter(KpiChatSession.chat_session_id == session_id)
        .first()
    )
    if sess is None or not sess.is_active:
        return None
    if sess.user_id != user_id:
        return None
    return sess


def create_session(
    db: Session, *, user_id: Optional[int], company_id: Optional[int],
    title: Optional[str] = None,
) -> KpiChatSession:
    sess = KpiChatSession(
        user_id=user_id,
        company_id=company_id,
        title=(title or None),
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def update_session_title(
    db: Session, session: KpiChatSession, title: str,
) -> KpiChatSession:
    session.title = (title or None)
    db.commit()
    db.refresh(session)
    return session


def soft_delete_session(db: Session, session: KpiChatSession) -> None:
    session.is_active = False
    db.commit()


# ---------------------------------------------------------------------------
# Turn pipeline — user prompt → agent → SQL → execute → save
# ---------------------------------------------------------------------------

def run_turn(
    db: Session,
    session: KpiChatSession,
    *,
    prompt: str,
    cfg,
    user_id: Optional[int],
    company_id: Optional[int],
    on_step: Optional[Callable[[Any], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[KpiChatMessage, KpiChatMessage]:
    """Execute one full turn end-to-end. Returns ``(user_msg, assistant_msg)``.

    Always persists both rows, even on failure — the assistant row
    carries the error so the conversation history reflects what happened.

    ``on_step`` and ``cancel_check`` are optional hooks used by the
    streaming variant: the agent loop fires ``on_step`` for each
    :class:`AgentStep` as it happens, and is told to abort whenever
    ``cancel_check()`` returns True.
    """
    # 1. Persist the user turn first so it's recoverable even if the agent crashes.
    user_msg = KpiChatMessage(
        chat_session_id=session.chat_session_id,
        role="user",
        content=prompt,
    )
    db.add(user_msg)

    # First-turn auto-title from the prompt, only when the user didn't set one.
    if not session.title:
        session.title = _derive_title(prompt)

    db.commit()
    db.refresh(user_msg)
    db.refresh(session)

    # 2. Resolve the LLM provider + caps via settings (DB → env → cfg fallback).
    eff = settings_service.get_effective(db, env=None)
    provider: Optional[LlmProvider] = eff.provider or cfg.llm_provider
    if provider is None:
        return user_msg, _save_assistant_failure(
            db, session, error="llm_disabled",
            content=(
                "The smart-analysis chatbot is disabled — no LLM provider "
                "is configured. Ask a SuperAdmin to set one in KPI Studio "
                "→ Settings."
            ),
        )

    # 3. Schema context — auto-introspect on first call.
    schema_payload = _ensure_schema(db, cfg)
    if schema_payload is None:
        return user_msg, _save_assistant_failure(
            db, session, error="schema_introspection_failed",
            content=(
                "Could not load the database schema. Check the "
                "uvicorn log and try again."
            ),
        )

    # 4. Run the agent. Reuse the exact same loop as the KPI editor.
    try:
        agent_result = nl2sql_agent.run_agent(
            provider=provider,
            schema=schema_payload,
            target_engine=cfg.target_engine,
            db=db,
            user_prompt=prompt,
            user_id=user_id,
            company_id=company_id,
            max_iterations=eff.max_iterations,
            token_budget=eff.token_budget,
            max_tokens_per_call=eff.max_tokens_per_call,
            on_step=on_step,
            cancel_check=cancel_check,
            system_prompt_extras=eff.domain_knowledge,
        )
    except Exception as exc:  # noqa: BLE001 — we always surface to the user
        log.exception("kpi_studio.chat: agent crashed")
        return user_msg, _save_assistant_failure(
            db, session, error="agent_error",
            content=f"Agent error: {exc}",
        )

    # 5. Execute the SQL if the agent proposed any.
    columns: Optional[list[str]] = None
    rows: Optional[list[list[Any]]] = None
    rewritten: Optional[str] = (
        agent_result.safety.rewritten if agent_result.safety else None
    )
    succeeded = bool(agent_result.sql) and agent_result.safety_error is None
    error: Optional[str] = agent_result.safety_error or agent_result.error

    if succeeded:
        try:
            exec_result = execute_safe_query(
                cfg.target_engine, db,
                sql=agent_result.sql,
                source="chat",
                user_id=user_id,
                company_id=company_id,
            )
            columns = exec_result.columns
            rows = exec_result.rows
            rewritten = exec_result.rewritten_sql
        except QueryExecutionError as exc:
            succeeded = False
            error = f"execution_failed: {exc}"

    # 6a. Auto-pick a chart type from the result shape (Phase B2).
    # Same heuristic as the KPI editor's preview suggestion. Stored as
    # JSON so the frontend renders the chart inline alongside the table,
    # and "Save as KPI" can pre-fill the chart config.
    chart_config: Optional[dict] = None
    chart_type_for_insight: Optional[str] = None
    if succeeded and columns is not None and rows is not None:
        suggestion = chart_picker.suggest_chart(columns, rows)
        chart_config = {
            "type": suggestion.type,
            "config": suggestion.config,
            # ``style`` left out — frontend's ChartRenderer applies the
            # default theme + animations when style is absent.
        }
        chart_type_for_insight = suggestion.type

    # 6b. Insight pass (Phase B3). Second LLM call reads the result and
    # produces a short narrative + actionable follow-ups. Failure here
    # never fails the turn — we just save the message without insight.
    insight_text: Optional[str] = None
    recommendations: Optional[list[str]] = None
    insight_tokens = 0
    insight_latency_ms = 0
    if succeeded and columns is not None and rows is not None:
        ins = insight_generator.generate_insight(
            provider=provider,
            user_prompt=prompt,
            sql=agent_result.sql or "",
            columns=columns,
            rows=rows,
            chart_type=chart_type_for_insight,
            max_tokens=min(eff.max_tokens_per_call, 800),
        )
        if ins.error:
            log.info("kpi_studio.chat: insight pass skipped: %s", ins.error)
        else:
            insight_text = ins.narrative or None
            recommendations = ins.recommendations or None
            insight_tokens = ins.tokens
            insight_latency_ms = ins.latency_ms

    # 6c. Persist the assistant turn — always, success or failure.
    assistant_msg = KpiChatMessage(
        chat_session_id=session.chat_session_id,
        role="assistant",
        content=agent_result.explanation or "",
        sql=(agent_result.sql or None),
        rewritten_sql=rewritten,
        result_columns=columns,
        result_rows=rows,
        chart_config=chart_config,
        agent_steps=[asdict(s) for s in agent_result.steps],
        insight=insight_text,
        recommendations=recommendations,
        succeeded=succeeded,
        error=(error[:500] if error else None),
        provider=agent_result.provider,
        model=agent_result.model,
        # Roll the insight pass's token + latency into the assistant
        # message so the audit trail reflects total cost of the turn.
        tokens=agent_result.total_tokens + insight_tokens,
        duration_ms=agent_result.total_latency_ms + insight_latency_ms,
    )
    db.add(assistant_msg)
    # Touching updated_at via SQLAlchemy onupdate requires a real change
    # — bump explicitly so the sessions list reorders on every turn.
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_msg)

    # 7. Rolling-summary compaction (Phase B3). Once a session grows past
    # the threshold, fold older messages into ``session.rolling_summary``
    # so subsequent turns can be primed with a compact recap instead of
    # the raw history. Failure leaves the existing summary alone.
    _maybe_compact_session(db, session, provider=provider)

    return user_msg, assistant_msg


def _maybe_compact_session(
    db: Session, session: KpiChatSession, *, provider: LlmProvider,
) -> None:
    """Refresh ``session.rolling_summary`` if enough new pairs have piled
    up since the last compaction. Best-effort — silently skips on any
    LLM failure so the user-visible turn isn't held hostage by a
    summariser hiccup."""
    db.refresh(session)
    all_messages = list(session.messages)  # already eager-loaded
    if not chat_summarizer.should_compact(all_messages):
        return

    to_summarise, _ = chat_summarizer.split_for_compaction(all_messages)
    summary = chat_summarizer.compact_summary(
        provider=provider,
        prior_summary=session.rolling_summary,
        new_messages=to_summarise,
    )
    if summary.error or not summary.text:
        log.info("kpi_studio.chat: summary pass skipped: %s", summary.error)
        return

    session.rolling_summary = summary.text
    db.commit()


def _save_assistant_failure(
    db: Session, session: KpiChatSession, *, error: str, content: str,
) -> KpiChatMessage:
    msg = KpiChatMessage(
        chat_session_id=session.chat_session_id,
        role="assistant",
        content=content,
        succeeded=False,
        error=error[:500],
    )
    db.add(msg)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


def _ensure_schema(db: Session, cfg):
    """Get the cached schema snapshot, auto-introspect on first miss."""
    snap = introspector.get_current_snapshot(db)
    if snap is not None:
        return introspector.load_payload(snap)
    try:
        payload = introspector.reflect_schema(cfg.target_engine, cfg)
        introspector.persist_snapshot(db, payload)
        return payload
    except Exception:
        log.exception("kpi_studio.chat: schema introspection failed")
        return None


# ---------------------------------------------------------------------------
# Streaming turn — drives the agent in a worker thread and yields SSE-shaped
# event dicts as they happen. Used by the chatbot composer's live timeline.
# ---------------------------------------------------------------------------

def _msg_to_dict(m: KpiChatMessage) -> dict:
    """Lightweight serialiser for the queue. The API endpoint re-validates
    this through the Pydantic ``ChatMessage`` model before sending out, so
    we keep the shape but don't depend on schema imports here."""
    return {
        "chat_message_id": m.chat_message_id,
        "chat_session_id": m.chat_session_id,
        "role": m.role,
        "content": m.content or "",
        "sql": m.sql,
        "rewritten_sql": m.rewritten_sql,
        "result_columns": m.result_columns,
        "result_rows": m.result_rows,
        "chart_config": m.chart_config,
        "agent_steps": m.agent_steps or None,
        "insight": m.insight,
        "recommendations": list(m.recommendations) if m.recommendations else None,
        "succeeded": m.succeeded,
        "error": m.error,
        "provider": m.provider,
        "model": m.model,
        "tokens": m.tokens,
        "duration_ms": m.duration_ms,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# Sentinel pushed onto the queue to signal "no more events" — avoids using
# `None` which a future event payload might legitimately carry.
_STREAM_END = object()


def run_turn_streaming(
    *,
    cfg,
    session_factory: Callable[[], Session],
    chat_session_id: int,
    prompt: str,
    user_id: Optional[int],
    company_id: Optional[int],
    cancel_event: threading.Event,
) -> Generator[dict, None, None]:
    """Run a turn in a worker thread, streaming events back to the caller.

    Event shapes (one dict per yield):

      * ``{"type": "step", "step": <AgentStep dict>}``
            Emitted as soon as each step is appended to the agent's log —
            this is what powers the live "Agent is doing X" timeline.
      * ``{"type": "done", "user_message": {...}, "assistant_message": {...}}``
            Final canonical payloads after persistence + insight generation.
      * ``{"type": "error", "error": "<message>"}``
            Anything that prevented a clean turn (session not found, agent
            crashed, DB error). Always followed by stream end.

    The worker thread carries its own SQLAlchemy session because Sessions
    are not thread-safe; the request thread's session stays untouched.
    Cancellation is signalled by setting ``cancel_event`` — the agent
    polls between iterations and emits an ``abort`` step before returning.
    """
    q: "queue.Queue[Any]" = queue.Queue()

    def worker() -> None:
        db = session_factory()
        try:
            sess = get_session(db, chat_session_id, user_id=user_id)
            if sess is None:
                q.put({"type": "error", "error": "Chat session not found."})
                return
            user_msg, assistant_msg = run_turn(
                db, sess,
                prompt=prompt,
                cfg=cfg,
                user_id=user_id,
                company_id=company_id,
                on_step=lambda s: q.put({"type": "step", "step": asdict(s)}),
                cancel_check=lambda: cancel_event.is_set(),
            )
            q.put({
                "type": "done",
                "user_message": _msg_to_dict(user_msg),
                "assistant_message": _msg_to_dict(assistant_msg),
            })
        except Exception as exc:  # noqa: BLE001
            log.exception("kpi_studio.chat: streaming turn failed")
            q.put({"type": "error", "error": str(exc)})
        finally:
            try:
                db.close()
            finally:
                q.put(_STREAM_END)

    thread = threading.Thread(target=worker, name="kpi-chat-stream", daemon=True)
    thread.start()

    try:
        while True:
            evt = q.get()
            if evt is _STREAM_END:
                break
            yield evt
    finally:
        # If the consumer abandoned us (client disconnect, exception in
        # the SSE handler), tell the worker to wind down cleanly so we
        # don't leak threads.
        cancel_event.set()
        thread.join(timeout=5)
