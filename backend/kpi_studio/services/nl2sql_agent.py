"""Agent orchestrator: drives the tool-use loop until the model emits
``propose_sql`` or hits an iteration / token cap (Phase A7).

Flow per turn:
  1. Send the running message history + tool descriptors to the provider.
  2. If the model emits text only → terminate (best-effort, treat as
     unsuccessful answer).
  3. If the model emits ``propose_sql`` → run the safety validator on
     the SQL, return the final answer.
  4. Otherwise → execute each tool the model called, append the JSON
     result as a ``tool``-role message, loop.

Caps:
  * ``max_iterations`` — hard cap on tool-call rounds (default 8).
  * ``token_budget``   — total prompt + completion tokens summed across
    rounds. Aborts the run cleanly when exceeded.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError, LlmTool,
)
from kpi_studio.schemas import SchemaPayload
from kpi_studio.services import nl2sql_tools as tools_mod
from kpi_studio.services.sql_safety import (
    SafeQuery, SqlSafetyError, validate_select_query,
)

log = logging.getLogger(__name__)


# Defaults — override via API request payload if needed.
DEFAULT_MAX_ITERATIONS = 8
DEFAULT_TOKEN_BUDGET = 50_000
DEFAULT_MAX_TOKENS_PER_CALL = 4_000


_SYSTEM_PROMPT = """\
You write {dialect} SELECT queries for a strictly read-only analytics
tool. The execution layer rejects anything that isn't a single SELECT
(DELETE / UPDATE / INSERT / DDL / EXEC / GRANT all fail safety
validation), so don't waste a turn proposing one — call ``propose_sql``
with sql="" and an explanation if the user asks for a write.

You work step-by-step, calling tools to inspect the schema and sample
data before proposing a final query.

Rules (strict):
1. Only emit a SELECT statement. No DDL, DML, or system tables.
2. Reference only tables and columns that appear in the schema you
   discover via ``list_tables`` and ``describe_table``.
3. Prefer explicit JOINs over subqueries when both work.
4. Always end the run by calling ``propose_sql`` with the final SQL and
   a 1-3 sentence explanation. If the schema can't answer the question,
   call propose_sql with sql="" and an explanation of why.
5. ``peek_distinct_values`` is for understanding categorical columns
   (status, region, type). Use it BEFORE filtering by string literals.
6. ``validate_sql`` is optional but cheap — call it once on a complex
   query before propose_sql to catch syntax issues.
7. Treat the *Application context* block (when present) as authoritative
   for business meaning — terms like "owner", "parent code", "location
   mapping", and entity lifecycles (enquiry → quotation → matured →
   …) are defined there. Use it to plan which tables / columns matter
   before you start exploring.

Be efficient — most questions need 2-4 tool calls before propose_sql.
"""


@dataclass
class AgentStep:
    """One observable event in the agent loop."""
    type: str  # "tool_call" | "tool_error" | "thought" | "final" | "abort"
    tool: Optional[str] = None
    args: Optional[dict] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


@dataclass
class AgentResult:
    """Full outcome of a run — what the API endpoint returns + audits."""
    sql: str
    explanation: str
    steps: list[AgentStep] = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    total_latency_ms: int = 0
    succeeded: bool = True
    error: Optional[str] = None
    safety: Optional[SafeQuery] = None
    safety_error: Optional[str] = None
    safety_findings: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""


class AgentBudgetExceeded(RuntimeError):
    """Raised when token usage crosses the configured budget. The
    orchestrator catches this and closes the run cleanly with a final
    ``abort`` step."""


class AgentCancelled(RuntimeError):
    """Raised when the caller-provided ``cancel_check`` returns True
    between iterations. The orchestrator turns this into a final
    ``abort`` step so the timeline reflects the user-initiated stop."""


def run_agent(
    *,
    provider: LlmProvider,
    schema: SchemaPayload,
    target_engine: Engine,
    db: Session,
    user_prompt: str,
    user_id: Optional[int] = None,
    company_id: Optional[int] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    max_tokens_per_call: int = DEFAULT_MAX_TOKENS_PER_CALL,
    on_step: Optional[Callable[[AgentStep], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    system_prompt_extras: Optional[str] = None,
) -> AgentResult:
    """Run the agent loop until ``propose_sql`` or a cap fires.

    ``on_step`` (optional) is invoked synchronously every time a step is
    appended to ``result.steps`` — used by the streaming chat endpoint to
    push agent activity to the client as it happens.

    ``cancel_check`` (optional) is polled at iteration boundaries; when it
    returns True the loop raises :class:`AgentCancelled` which the caller
    surfaces as a final ``abort`` step.

    ``system_prompt_extras`` (optional) is admin-curated business context
    (the System Knowledge Hub) appended to the system message under an
    "Application context" header so the LLM has domain meaning before it
    starts exploring the schema.
    """
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        raise ValueError("user_prompt is required")

    def _emit(step: AgentStep) -> None:
        """Append a step to the result *and* notify the live listener.
        Listener exceptions are swallowed — a flaky callback must never
        derail the underlying agent run."""
        result.steps.append(step)
        if on_step is not None:
            try:
                on_step(step)
            except Exception:  # noqa: BLE001
                log.exception("kpi_studio.nl2sql_agent: on_step callback failed")

    safe_dialect = (
        "tsql" if target_engine.dialect.name == "mssql" else target_engine.dialect.name
    )
    dialect_label = "T-SQL" if safe_dialect == "tsql" else safe_dialect.upper()

    ctx = tools_mod.ToolContext(
        schema=schema,
        target_engine=target_engine,
        db=db,
        user_id=user_id,
        company_id=company_id,
        safe_dialect=safe_dialect,
    )

    # Compose the system message: base prompt + (optional) admin-curated
    # Application context block. Wrapped in clear delimiters so the model
    # treats the extras as authoritative domain knowledge, not user data.
    system_content = _SYSTEM_PROMPT.format(dialect=dialect_label)
    extras = (system_prompt_extras or "").strip()
    if extras:
        system_content = (
            f"{system_content}\n"
            "--- Application context (authoritative business domain) ---\n"
            f"{extras}\n"
            "--- End application context ---\n"
        )

    messages: list[LlmMessage] = [
        LlmMessage(role="system", content=system_content),
        LlmMessage(role="user", content=user_prompt),
    ]

    result = AgentResult(
        sql="",
        explanation="",
        provider=getattr(provider, "name", "unknown"),
        model="",
    )
    started = time.perf_counter()

    def _check_cancelled() -> None:
        if cancel_check is not None and cancel_check():
            raise AgentCancelled("user_cancelled")

    try:
        for iteration in range(max_iterations):
            result.iterations = iteration + 1

            # Poll for user-initiated stop before each LLM round. Mid-tool
            # cancellation isn't possible (tools are blocking), but the
            # agent loop is the dominant cost so the responsiveness is
            # already good enough — a stop while the LLM is calling out
            # gets handled at the next boundary.
            _check_cancelled()

            try:
                turn = provider.complete_with_tools(
                    messages,
                    tools_mod.ALL_TOOLS,
                    max_tokens=max_tokens_per_call,
                )
            except LlmProviderError:
                # Bubble up to the API layer as 502 — agent shouldn't
                # swallow provider failures.
                raise

            result.model = turn.model
            result.total_tokens += int(turn.usage.get("total_tokens") or 0)

            # Budget check — fire-and-stop with a clean abort step.
            if result.total_tokens > token_budget:
                _emit(AgentStep(
                    type="abort",
                    error=(
                        f"Token budget exceeded: {result.total_tokens} > {token_budget}. "
                        "Refine your prompt or raise KPI_NL_TOKEN_BUDGET."
                    ),
                ))
                result.succeeded = False
                result.error = "token_budget_exceeded"
                return result

            # No tool calls + non-empty content → model gave up on
            # tool-use and just answered as text. Treat the content as
            # the explanation, leave SQL empty, terminate.
            if not turn.tool_calls:
                _emit(AgentStep(type="thought", output=turn.content))
                result.explanation = turn.content or "Model responded without proposing SQL."
                result.succeeded = bool(turn.content)
                if not turn.content:
                    result.error = "empty_model_response"
                return result

            # Append the assistant turn so subsequent calls can match
            # tool_call_id. We pass the raw OpenAI message dict as the
            # content and let _serialize_message accept it as-is — but
            # the OpenAI provider already preserves the right shape on
            # raw_assistant_message; here we just shove it through a
            # transparent LlmMessage carrier.
            assistant_msg = LlmMessage(
                role="assistant",
                content=turn.raw_assistant_message.get("content") or "",
                tool_calls=turn.tool_calls,
            )
            messages.append(assistant_msg)

            # Process each tool call. If propose_sql shows up, terminate
            # immediately — even if the model bundled other tool calls
            # alongside it (which OpenAI sometimes does).
            for tc in turn.tool_calls:
                if tc.name == "propose_sql":
                    _emit(AgentStep(
                        type="final",
                        tool="propose_sql",
                        args=tc.arguments,
                    ))
                    sql = (tc.arguments.get("sql") or "").strip()
                    explanation = (tc.arguments.get("explanation") or "").strip()
                    result.sql = sql
                    result.explanation = explanation
                    if sql:
                        try:
                            result.safety = validate_select_query(
                                sql, dialect=safe_dialect,
                            )
                        except SqlSafetyError as exc:
                            result.safety_error = str(exc)
                            result.safety_findings = list(
                                getattr(exc, "findings", []) or []
                            )
                            log.info(
                                "kpi_studio.nl2sql_agent: validation failed: %s",
                                result.safety_error,
                            )
                    return result

                step_started = time.perf_counter()
                try:
                    output = tools_mod.dispatch(tc.name, tc.arguments, ctx)
                    step_latency = int((time.perf_counter() - step_started) * 1000)
                    _emit(AgentStep(
                        type="tool_call",
                        tool=tc.name,
                        args=tc.arguments,
                        output=output,
                        latency_ms=step_latency,
                    ))
                    tool_content = json.dumps(output, default=str)
                except tools_mod.ToolError as exc:
                    step_latency = int((time.perf_counter() - step_started) * 1000)
                    _emit(AgentStep(
                        type="tool_error",
                        tool=tc.name,
                        args=tc.arguments,
                        error=str(exc),
                        latency_ms=step_latency,
                    ))
                    # Surface the error back to the model so it can correct.
                    tool_content = json.dumps({"error": str(exc)})

                messages.append(LlmMessage(
                    role="tool",
                    content=tool_content,
                    tool_call_id=tc.id,
                ))

        # Iteration cap reached without a propose_sql.
        _emit(AgentStep(
            type="abort",
            error=(
                f"Reached iteration limit ({max_iterations}) without a final "
                "answer. Refine your prompt or raise KPI_NL_MAX_ITERATIONS."
            ),
        ))
        result.succeeded = False
        result.error = "iteration_limit"
        return result

    except AgentCancelled:
        _emit(AgentStep(type="abort", error="cancelled_by_user"))
        result.succeeded = False
        result.error = "cancelled"
        return result

    finally:
        result.total_latency_ms = int((time.perf_counter() - started) * 1000)
