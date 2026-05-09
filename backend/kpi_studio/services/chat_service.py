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
from kpi_studio.providers.llm.base import LlmMessage, LlmProvider
from kpi_studio.services import (
    chart_picker, chat_summarizer, insight_generator, introspector,
    nl2sql_agent, preflight, settings_service,
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


_HISTORY_SQL_SNIPPET = 300


def _load_recent_history(
    db: Session,
    session: KpiChatSession,
    n_turns: int,
    *,
    before_msg_id: Optional[int] = None,
) -> list[LlmMessage]:
    """Load up to ``n_turns`` (user, assistant) pairs from this chat
    session for replay into the LLM context. Excludes any message
    whose id >= ``before_msg_id`` so the just-persisted current user
    turn doesn't get fed in twice.

    Assistant turns include a trailing ``[Previous SQL: …]`` marker
    when SQL was produced — that's what lets follow-ups like "now
    group that by region" resolve "that" correctly. SQL is truncated
    to 300 chars (single-line) to keep the prompt cheap; the agent
    can re-derive the full SQL by re-running its tools if it needs
    to."""
    if n_turns <= 0:
        return []

    q = db.query(KpiChatMessage).filter(
        KpiChatMessage.chat_session_id == session.chat_session_id,
    )
    if before_msg_id is not None:
        q = q.filter(KpiChatMessage.chat_message_id < before_msg_id)
    # Pull a few extras (n_turns * 2 + 1) so we don't end up with a
    # dangling assistant whose user turn fell off the cliff.
    rows = (
        q.order_by(desc(KpiChatMessage.created_at))
        .limit(n_turns * 2 + 1)
        .all()
    )
    rows.reverse()

    out: list[LlmMessage] = []
    for m in rows:
        if m.role == "user":
            out.append(LlmMessage(role="user", content=(m.content or "")))
        elif m.role == "assistant":
            content = (m.content or "").strip()
            if m.sql:
                sql_compact = " ".join((m.sql or "").split())
                if len(sql_compact) > _HISTORY_SQL_SNIPPET:
                    sql_compact = sql_compact[:_HISTORY_SQL_SNIPPET] + "…"
                content = (
                    f"{content}\n\n[Previous SQL: {sql_compact}]"
                    if content else
                    f"[Previous SQL: {sql_compact}]"
                )
            if not content:
                continue  # skip empty assistant turns (failed runs)
            out.append(LlmMessage(role="assistant", content=content))
    # Drop a leading orphan assistant — happens when the slice opens
    # mid-pair. Keeping it would put the LLM in a state where the
    # first message is a model reply with no preceding user turn.
    while out and out[0].role == "assistant":
        out.pop(0)
    return out


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

def _friendly_failure_message(error_code: Optional[str]) -> str:
    """Translate an internal error code into a plain-English explanation
    the end user can act on. The original error code is still preserved
    on the abort step inside ``agent_steps`` for admin/debug visibility,
    but the user-facing message in the assistant bubble must not leak
    DB IDs, table names, env-var names, or 'token_budget'-style jargon."""
    code = (error_code or "").lower()
    if "token_budget" in code:
        return (
            "That question turned out to be more involved than I could "
            "process in one go. Could you try breaking it into a few smaller, "
            "more focused questions?"
        )
    if "iteration_limit" in code:
        return (
            "I went back and forth without landing on a clear answer. "
            "Could you rephrase what you'd like to see, or be a bit more "
            "specific about which records or time period you mean?"
        )
    if "execution_failed" in code:
        return (
            "I had trouble pulling that data from the database. "
            "Could you try asking it a different way, or with a narrower "
            "filter?"
        )
    if "cancelled" in code:
        return "Stopped at your request."
    if "safety" in code or "validation" in code:
        return (
            "I came up with a query, but it didn't pass our read-only safety "
            "check. Could you rephrase your question? The chatbot can only "
            "look up data, not change it."
        )
    if "provider_error" in code or "agent_error" in code:
        return (
            "Something went wrong on the AI service. Please try again in a "
            "moment — if it keeps happening, let an admin know."
        )
    if "schema" in code:
        return (
            "I couldn't load the database structure to answer that. "
            "Please try again in a moment, or ask an admin to check the "
            "server."
        )
    if "llm_disabled" in code:
        return (
            "The smart-analysis chatbot is disabled — no AI provider is "
            "configured. Ask a SuperAdmin to set one in KPI Studio → Settings."
        )
    if "empty_model_response" in code or "empty" in code:
        return (
            "I couldn't come up with an answer for that. Could you rephrase "
            "your question, or give me a hint about which records you mean?"
        )
    return (
        "Something went wrong while processing your question. Please try "
        "again, or rephrase the question."
    )


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
            content=_friendly_failure_message("llm_disabled"),
        )

    # 3. Schema context — auto-introspect on first call.
    schema_payload = _ensure_schema(db, cfg)
    if schema_payload is None:
        return user_msg, _save_assistant_failure(
            db, session, error="schema_introspection_failed",
            content=_friendly_failure_message("schema_introspection_failed"),
        )

    # 3b. Phase B2 — recent (user, assistant) pairs for follow-up context.
    # Threaded into both preflight (intent disambiguation) and the SQL
    # agent (so "group THAT by region" can resolve "that" against the
    # last query). Excludes the just-persisted current user turn.
    recent_history = _load_recent_history(
        db, session,
        n_turns=eff.chat_history_turns,
        before_msg_id=user_msg.chat_message_id,
    )

    # 4a. Pre-flight Planner ↔ Resolver loop. Validates the user's
    # prompt against the System Knowledge Hub + schema before the SQL
    # agent runs. Three outcomes:
    #   - ready    : we have a clean intent; the SQL agent gets the
    #                Planner's intent as ``user_prompt`` and the user's
    #                raw text as ``original_prompt`` so it can mirror
    #                the user's voice in its explanation.
    #   - ask_user : ambiguity remains. We persist a ``clarify`` turn
    #                and skip the SQL agent entirely.
    #   - abort    : provider/budget failure. Fall back to running the
    #                SQL agent on the raw prompt — better than blocking.
    sql_user_prompt = prompt
    sql_original_prompt: Optional[str] = None
    if eff.preflight_enabled:
        try:
            preflight_verdict = preflight.run_preflight(
                provider=provider,
                schema=schema_payload,
                user_prompt=prompt,
                domain_knowledge=eff.domain_knowledge,
                max_rounds=eff.preflight_max_rounds,
                history=recent_history,
                on_step=(
                    (lambda s: on_step(_preflight_step_to_agent_step(s)))
                    if on_step is not None else None
                ),
                cancel_check=cancel_check,
            )
        except Exception:  # noqa: BLE001
            log.exception("kpi_studio.chat: preflight crashed; falling back")
            preflight_verdict = None
        if preflight_verdict and preflight_verdict.status == "ask_user":
            return user_msg, _save_assistant_clarify(
                db, session, verdict=preflight_verdict,
            )
        if preflight_verdict and preflight_verdict.status == "ready":
            sql_user_prompt = (preflight_verdict.intent or prompt).strip() or prompt
            sql_original_prompt = prompt
        # status == 'abort' or None → leave sql_user_prompt as the raw
        # prompt; SQL agent runs as it did before preflight existed.

    # 4b. Run the agent. Wire the executor as a callback so the agent
    # can see SQL execution errors and retry up to 3 times instead of
    # surfacing the first failure to the user. Bumps the iteration cap
    # by max_sql_retries so retries don't starve the schema-discovery
    # phase.
    def _exec_for_agent(sql: str) -> nl2sql_agent.ExecutedSqlResult:
        """Adapter: execute_safe_query → ExecutedSqlResult. Re-raises
        QueryExecutionError so the agent's tool-error path catches it
        with the human-readable DB message intact."""
        out = execute_safe_query(
            cfg.target_engine, db,
            sql=sql,
            source="chat",
            user_id=user_id,
            company_id=company_id,
        )
        return nl2sql_agent.ExecutedSqlResult(
            columns=list(out.columns),
            rows=list(out.rows),
            rewritten_sql=out.rewritten_sql or sql,
        )

    sql_retries = 3
    try:
        agent_result = nl2sql_agent.run_agent(
            provider=provider,
            schema=schema_payload,
            target_engine=cfg.target_engine,
            db=db,
            user_prompt=sql_user_prompt,
            original_prompt=sql_original_prompt,
            user_id=user_id,
            company_id=company_id,
            # Headroom so the schema-discovery phase isn't starved by
            # retries — 3 retries can each consume an extra round.
            max_iterations=max(eff.max_iterations, eff.max_iterations + sql_retries),
            token_budget=eff.token_budget,
            max_tokens_per_call=eff.max_tokens_per_call,
            history=recent_history,
            on_step=on_step,
            cancel_check=cancel_check,
            system_prompt_extras=eff.domain_knowledge,
            execute_sql_fn=_exec_for_agent,
            max_sql_retries=sql_retries,
        )
    except Exception as exc:  # noqa: BLE001 — we always surface to the user
        log.exception("kpi_studio.chat: agent crashed")
        # Technical exception text stays in the log + on the abort step's
        # ``output`` (when one was emitted); the message body itself shows
        # the user a plain-English explanation.
        return user_msg, _save_assistant_failure(
            db, session, error="agent_error",
            content=_friendly_failure_message("agent_error"),
        )

    # 5. Execution result. The agent owns execution now (see
    # ``_exec_for_agent`` above), so the columns/rows are already on
    # the result. We fall back to running the executor here only when
    # the agent's executor path didn't fire (e.g. no SQL proposed).
    columns: Optional[list[str]] = agent_result.executed_columns
    rows: Optional[list[list[Any]]] = agent_result.executed_rows
    rewritten: Optional[str] = (
        agent_result.executed_rewritten_sql
        or (agent_result.safety.rewritten if agent_result.safety else None)
    )
    succeeded = bool(agent_result.sql) and agent_result.safety_error is None \
        and agent_result.error is None
    error: Optional[str] = agent_result.safety_error or agent_result.error

    # Defensive fallback: if the agent has SQL but no executed_* (legacy
    # path or odd termination), run the executor here. Normal flow has
    # already populated columns/rows above.
    if succeeded and columns is None:
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
    # On failure the ``content`` is replaced with a plain-English message
    # produced from the internal ``error`` code, and the ``error`` field
    # itself is cleared on the persisted row so the frontend's red error
    # block doesn't double-render the same information in technical form.
    # The original error code is still stamped on the abort step inside
    # ``agent_steps`` (and in our log), so admins keep their audit trail.
    if succeeded:
        message_content = agent_result.explanation or ""
        message_error: Optional[str] = (error[:500] if error else None)
    else:
        message_content = _friendly_failure_message(error)
        message_error = None
    assistant_msg = KpiChatMessage(
        chat_session_id=session.chat_session_id,
        role="assistant",
        content=message_content,
        sql=(agent_result.sql or None),
        rewritten_sql=rewritten,
        result_columns=columns,
        result_rows=rows,
        chart_config=chart_config,
        agent_steps=[asdict(s) for s in agent_result.steps],
        insight=insight_text,
        recommendations=recommendations,
        succeeded=succeeded,
        error=message_error,
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
    """Persist a failed turn with a plain-English ``content``. The
    technical ``error`` code is logged for admins but NOT stored on the
    persisted message — leaving it None means the frontend's red error
    block won't double-render the same information in technical form.
    The user just sees the friendly explanation in the bubble."""
    log.info(
        "kpi_studio.chat: assistant failure persisted (code=%s)", error,
    )
    msg = KpiChatMessage(
        chat_session_id=session.chat_session_id,
        role="assistant",
        content=content,
        succeeded=False,
        error=None,
    )
    db.add(msg)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


def _save_assistant_clarify(
    db: Session, session: KpiChatSession, *, verdict,
) -> KpiChatMessage:
    """Persist a ``kind='clarify'`` assistant turn — Planner's question
    to the user. No SQL / chart / insight; the next user turn restarts
    the loop with the user's clarification as the new prompt.

    The Planner-Resolver step transcript is stashed on ``agent_steps``
    so the timeline replays correctly when the user reopens the
    session, and ``recommendations`` carries the suggested-options
    chips so the frontend can render one-tap reply buttons.
    """
    question = (verdict.user_question or "").strip() or "Could you clarify your question?"
    options = list(verdict.suggested_options or [])
    msg = KpiChatMessage(
        chat_session_id=session.chat_session_id,
        role="assistant",
        kind="clarify",
        content=question,
        succeeded=True,  # not a failure — this is a successful clarify turn
        agent_steps=[asdict(s) for s in verdict.steps] if verdict.steps else None,
        recommendations=options or None,
        tokens=verdict.total_tokens or 0,
        error=verdict.error[:500] if verdict.error else None,
    )
    db.add(msg)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)
    return msg


def _preflight_step_to_agent_step(step) -> Any:
    """Adapt a preflight ``PreflightStep`` to the ``AgentStep`` shape
    so the streaming endpoint's ``on_step`` callback can handle both
    sources without per-source plumbing. The fields line up 1:1; we
    just rename the dataclass so dataclasses.asdict treats it as one."""
    from kpi_studio.services.nl2sql_agent import AgentStep
    return AgentStep(
        type=step.type,
        tool=step.tool,
        args=step.args,
        output=step.output,
        error=step.error,
        latency_ms=step.latency_ms,
    )


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
        "kind": getattr(m, "kind", "answer") or "answer",
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
