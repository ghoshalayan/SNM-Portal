"""Pre-flight Planner / Resolver loop for the chatbot.

Goal: catch ambiguous or out-of-scope questions before the (expensive)
nl2sql_agent runs. Two roles bound into one LLM tool-use loop:

* **Planner** — the LLM. Reads the user prompt, the System Knowledge
  Hub blob, and the schema overview. Decides whether to ask the
  resolver for more context, or to commit to a final verdict.
* **Resolver** — the deterministic Python tools the LLM calls to look
  things up. Three for v1: ``lookup_domain``, ``find_table``,
  ``find_column``. Cheap text/dict searches, no LLM round-trip needed.

The loop terminates when the LLM calls the special ``finalize`` tool
with one of two verdicts:

* ``ready``     — disambiguated. Returns a clean ``intent`` string that
                 the SQL agent will use as ``user_prompt`` (with the
                 user's *original* prompt also passed through as
                 ``original_prompt`` so the agent can mirror the user's
                 voice in its explanation).
* ``ask_user``  — Planner can't disambiguate from context alone. Pre-
                 flight returns the question to chat_service, which
                 persists it as a ``kind='clarify'`` assistant turn.

Round cap is supplied by EffectiveSettings (default 5, clamped 1..10).
The cap protects against pathological loops and runaway LLM cost; the
final round forces ``finalize`` and rejects anything else with an abort.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmTool,
)
from kpi_studio.schemas import SchemaPayload

log = logging.getLogger(__name__)


# Caps deliberately conservative — Planner+Resolver should converge in
# 1-2 rounds on typical prompts. Anything beyond that is usually a sign
# the Planner is stuck and we should escalate to the user.
DEFAULT_MAX_TOKENS_PER_CALL = 800
DEFAULT_TOTAL_TOKEN_BUDGET = 6_000


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

@dataclass
class PreflightStep:
    """One observable event in the Planner ↔ Resolver loop. Streamed to
    the frontend via the same SSE channel as nl2sql_agent's AgentSteps,
    rendered with planner_*/resolver_* icons in the live timeline."""
    type: str  # 'planner_question' | 'resolver_answer' | 'final' | 'abort'
    tool: Optional[str] = None
    args: Optional[dict] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


@dataclass
class PreflightVerdict:
    """Outcome of the loop. Status drives chat_service's branch."""
    status: str  # 'ready' | 'ask_user' | 'abort'
    # When status == 'ready':
    intent: Optional[str] = None
    tables_likely_needed: List[str] = field(default_factory=list)
    # When status == 'ask_user':
    user_question: Optional[str] = None
    suggested_options: List[str] = field(default_factory=list)
    # Always populated:
    rounds_used: int = 0
    total_tokens: int = 0
    steps: List[PreflightStep] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Resolver tools — deterministic Python, no LLM round-trip
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", (s or "").lower()).strip()


def lookup_domain(domain_knowledge: Optional[str], query: str) -> dict:
    """Substring + token-overlap match against the System Knowledge Hub
    blob. Returns up to 3 paragraphs that mention any non-trivial token
    of the query. No LLM cost — pure string match.
    """
    if not domain_knowledge:
        return {"matches": [], "note": "No domain knowledge configured."}
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", domain_knowledge) if p.strip()]
    tokens = [t for t in _norm(query).split() if len(t) > 2]
    if not tokens:
        return {"matches": [], "note": "Query was too short to search."}
    scored: list[tuple[int, str]] = []
    for p in paragraphs:
        norm_p = _norm(p)
        score = sum(1 for t in tokens if t in norm_p)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[:3]]
    return {
        "matches": top,
        "note": (
            f"{len(top)} paragraph(s) matched on "
            f"{', '.join(repr(t) for t in tokens[:5])}"
            if top else "No matching paragraphs."
        ),
    }


def find_table(schema: SchemaPayload, concept: str) -> dict:
    """Fuzzy match table names against a concept. Returns the top
    matching tables with their column names so the Planner can decide
    if any of them carry the columns it needs."""
    q = _norm(concept)
    if not q:
        return {"matches": []}
    tokens = [t for t in q.split() if len(t) > 1]
    scored: list[tuple[int, dict]] = []
    for table in schema.tables:
        name_norm = _norm(table.name)
        score = sum(1 for t in tokens if t in name_norm)
        if score == 0 and q in name_norm:
            score = 1
        if score:
            scored.append((score, {
                "name": table.name,
                # Cap columns to keep the Resolver response tight; the
                # Planner can ask `find_column` for a deeper look.
                "columns": [c.name for c in table.columns][:30],
            }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return {"matches": [m for _, m in scored[:5]]}


def find_column(
    schema: SchemaPayload, concept: str, table: Optional[str] = None,
) -> dict:
    """Fuzzy match column names. Optionally scope to one table."""
    q = _norm(concept)
    if not q:
        return {"matches": []}
    tokens = [t for t in q.split() if len(t) > 1]
    scoped = (
        [t for t in schema.tables if _norm(t.name) == _norm(table)]
        if table else schema.tables
    )
    matches: list[dict] = []
    for t in scoped:
        for col in t.columns:
            name_norm = _norm(col.name)
            if any(tok in name_norm for tok in tokens) or q in name_norm:
                matches.append({
                    "table": t.name,
                    "column": col.name,
                    "type": str(getattr(col, "data_type", "") or ""),
                })
    return {"matches": matches[:10]}


# ---------------------------------------------------------------------------
# Tool descriptors for the LLM
# ---------------------------------------------------------------------------

_TOOLS: list[LlmTool] = [
    LlmTool(
        name="lookup_domain",
        description=(
            "Search the company's System Knowledge Hub for a term or phrase. "
            "Use this FIRST when the user mentions business-specific words "
            "(owner, parent code, FOR delivery, viability, etc.) — the answer "
            "is almost certainly in the curated domain blob."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Term or short phrase to search for.",
                },
            },
            "required": ["query"],
        },
    ),
    LlmTool(
        name="find_table",
        description=(
            "Find tables in the database whose names match a concept. "
            "Returns up to 5 candidates with their column names. Use "
            "before deciding the user's question is unanswerable."
        ),
        parameters={
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "Business concept like 'quotation', 'site', 'enquiry follow-up'.",
                },
            },
            "required": ["concept"],
        },
    ),
    LlmTool(
        name="find_column",
        description=(
            "Find columns matching a concept. Optionally scope to one "
            "table. Use to confirm a specific attribute exists before "
            "committing to an intent."
        ),
        parameters={
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "Attribute concept like 'created date', 'owner user', 'amount'.",
                },
                "table": {
                    "type": "string",
                    "description": "Optional: restrict the search to this table.",
                },
            },
            "required": ["concept"],
        },
    ),
    LlmTool(
        name="finalize",
        description=(
            "Terminate the pre-flight loop with a verdict. Call this "
            "EXACTLY ONCE, on the round where you have enough info "
            "(status=ready) or you genuinely need help (status=ask_user)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ready", "ask_user"],
                    "description": (
                        "ready = proceed with the SQL agent; "
                        "ask_user = single follow-up question to the user."
                    ),
                },
                "intent": {
                    "type": "string",
                    "description": (
                        "When status=ready: a one-sentence rephrasing of "
                        "what the user wants in schema-aware terms. The "
                        "SQL agent uses this as its prompt."
                    ),
                },
                "tables_likely_needed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "When status=ready: candidate table names.",
                },
                "user_question": {
                    "type": "string",
                    "description": (
                        "When status=ask_user: ONE concrete question for the user. "
                        "Be specific — 'do you mean Approved or Matured?' beats "
                        "'could you clarify?'"
                    ),
                },
                "suggested_options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "When status=ask_user: short option strings the user can "
                        "click as chips to answer in one tap."
                    ),
                },
            },
            "required": ["status"],
        },
    ),
]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the pre-flight checker for a {dialect} read-only analytics
chatbot. Your only job is to decide whether the user's question can be
answered from the available context, OR whether ONE clarifying question
to the user would unblock it.

You have lookup tools (lookup_domain / find_table / find_column) and a
``finalize`` tool that ends the loop with a verdict. You MUST call
``finalize`` exactly once, no later than round {max_rounds}.

Decision rules (strict):

1. Default to ``ready``. The downstream SQL agent has its own schema
   tools and is good at narrowing things down; you only need to make
   sure the question isn't fundamentally ambiguous or out of scope.

2. Use ``ask_user`` ONLY when there are genuinely two or more plausible
   interpretations and one short follow-up would pick between them.
   Before asking, ALWAYS try ``lookup_domain`` first — the System
   Knowledge Hub almost certainly has the answer for any business term
   that sounds domain-specific.

3. NEVER write SQL. Don't propose a query. Just produce the intent
   statement (when ready) so the SQL agent can take over.

4. Don't restate the user's prompt verbatim. ``intent`` should be a
   crisp, schema-aware rephrasing — name the actual table(s) when
   you're confident; otherwise describe the entity in domain terms.

5. The System Knowledge Hub is the authoritative source for business
   meaning. Use ``lookup_domain`` to query it instead of guessing or
   asking the user. Domain knowledge is{domain_status}.

SCHEMA OVERVIEW (table names only — use find_table for column lists):
{table_list}
"""


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

def run_preflight(
    *,
    provider: LlmProvider,
    schema: SchemaPayload,
    user_prompt: str,
    domain_knowledge: Optional[str],
    max_rounds: int = 5,
    max_tokens_per_call: int = DEFAULT_MAX_TOKENS_PER_CALL,
    token_budget: int = DEFAULT_TOTAL_TOKEN_BUDGET,
    history: Optional[list[LlmMessage]] = None,
    on_step: Optional[Callable[[PreflightStep], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> PreflightVerdict:
    """Drive the Planner ↔ Resolver loop until ``finalize`` is called.

    Behaves like ``nl2sql_agent.run_agent`` — same callback shape so
    chat_service can stream both timelines through the same SSE
    channel without per-source plumbing."""
    safe_dialect = "T-SQL"
    table_list = ", ".join(t.name for t in schema.tables) or "(no tables introspected)"
    # Phase B2 — the entire ``domain_knowledge`` blob used to be inlined
    # here, which left almost no preflight token budget for actual
    # reasoning. The blob is now reachable only via the ``lookup_domain``
    # tool (which is what the tool exists for); we just tell the model
    # whether anything is configured so it knows whether the call is
    # worth making.
    domain_status = "configured — call lookup_domain to query it" if (
        domain_knowledge and domain_knowledge.strip()
    ) else "not configured"
    sys_prompt = _SYSTEM_PROMPT.format(
        dialect=safe_dialect,
        max_rounds=max_rounds,
        domain_status=domain_status,
        table_list=table_list,
    )

    # Phase B2 — recent turns precede the latest user prompt so the
    # planner can resolve follow-up references like "now group that
    # by region" or "and only for last quarter" against the actual
    # prior turns of the conversation rather than guessing.
    messages: list[LlmMessage] = [
        LlmMessage(role="system", content=sys_prompt),
    ]
    if history:
        messages.extend(history)
    messages.append(LlmMessage(role="user", content=user_prompt.strip()))
    verdict = PreflightVerdict(status="abort")

    def _emit(step: PreflightStep) -> None:
        verdict.steps.append(step)
        if on_step is not None:
            try:
                on_step(step)
            except Exception:  # noqa: BLE001
                log.exception("kpi_studio.preflight: on_step callback failed")

    def _cancelled() -> bool:
        return cancel_check is not None and cancel_check()

    for iteration in range(max_rounds):
        verdict.rounds_used = iteration + 1
        if _cancelled():
            _emit(PreflightStep(
                type="abort",
                error="Stopped at your request.",
                output={"kind": "cancelled_by_user"},
            ))
            verdict.error = "cancelled"
            return verdict

        try:
            turn = provider.complete_with_tools(
                messages, _TOOLS, max_tokens=max_tokens_per_call,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("kpi_studio.preflight: provider failed")
            # User-facing label is plain English; technical exception
            # message lives on ``output`` for the admin-facing reasoning
            # panel.
            _emit(PreflightStep(
                type="abort",
                error="The AI service ran into a problem.",
                output={"kind": "provider_error", "details": str(exc)[:500]},
            ))
            verdict.error = "provider_error"
            return verdict

        verdict.total_tokens += int(turn.usage.get("total_tokens") or 0)
        if verdict.total_tokens > token_budget:
            _emit(PreflightStep(
                type="abort",
                error="Question is too involved to scope in one shot.",
                output={
                    "kind": "token_budget",
                    "tokens_used": verdict.total_tokens,
                    "budget": token_budget,
                },
            ))
            verdict.error = "token_budget"
            return verdict

        # Append the assistant turn so subsequent rounds see the tool-use thread.
        messages.append(LlmMessage(
            role="assistant",
            content=turn.raw_assistant_message.get("content") or "",
            tool_calls=turn.tool_calls,
        ))

        # No tool calls + text only → coerce to ask_user with the model's
        # text. Better than aborting; the user at least sees something.
        if not turn.tool_calls:
            text = (turn.content or "").strip() or "Could you clarify your question?"
            _emit(PreflightStep(type="final", tool="finalize",
                                args={"status": "ask_user"}, output=text))
            verdict.status = "ask_user"
            verdict.user_question = text
            return verdict

        # Process tools in order. ``finalize`` always wins — even if the
        # model bundled it alongside another lookup, we honour it first.
        for tc in turn.tool_calls:
            if tc.name == "finalize":
                args = tc.arguments or {}
                status = (args.get("status") or "").lower()
                if status == "ready":
                    _emit(PreflightStep(type="final", tool="finalize", args=args))
                    verdict.status = "ready"
                    verdict.intent = (args.get("intent") or "").strip() or user_prompt
                    tables = args.get("tables_likely_needed") or []
                    if isinstance(tables, list):
                        verdict.tables_likely_needed = [str(t) for t in tables]
                elif status == "ask_user":
                    _emit(PreflightStep(type="final", tool="finalize", args=args))
                    verdict.status = "ask_user"
                    verdict.user_question = (args.get("user_question") or "").strip() \
                        or "Could you clarify your question?"
                    options = args.get("suggested_options") or []
                    if isinstance(options, list):
                        verdict.suggested_options = [str(o) for o in options][:6]
                else:
                    # Unrecognised status → treat as abort so the SQL
                    # agent never runs on a malformed verdict.
                    _emit(PreflightStep(
                        type="abort",
                        error="The pre-flight check returned an unexpected result.",
                        output={"kind": "bad_finalize_status", "status": status},
                    ))
                    verdict.error = "bad_finalize_status"
                return verdict

            # Resolver tool dispatch — Python only.
            import time
            t0 = time.perf_counter()
            try:
                if tc.name == "lookup_domain":
                    output = lookup_domain(domain_knowledge, tc.arguments.get("query") or "")
                elif tc.name == "find_table":
                    output = find_table(schema, tc.arguments.get("concept") or "")
                elif tc.name == "find_column":
                    output = find_column(
                        schema,
                        tc.arguments.get("concept") or "",
                        tc.arguments.get("table"),
                    )
                else:
                    output = {"error": f"unknown tool: {tc.name}"}
                latency = int((time.perf_counter() - t0) * 1000)
                _emit(PreflightStep(
                    type="resolver_answer", tool=tc.name,
                    args=tc.arguments, output=output, latency_ms=latency,
                ))
                tool_content = json.dumps(output, default=str)
            except Exception as exc:  # noqa: BLE001
                latency = int((time.perf_counter() - t0) * 1000)
                _emit(PreflightStep(
                    type="resolver_answer", tool=tc.name,
                    args=tc.arguments, error=str(exc), latency_ms=latency,
                ))
                tool_content = json.dumps({"error": str(exc)})

            messages.append(LlmMessage(
                role="tool", content=tool_content, tool_call_id=tc.id,
            ))

    # Round cap reached without finalize. Force ready with the user's
    # raw prompt as the intent — let the SQL agent take its shot rather
    # than blocking the user. The abort step is still emitted so the
    # timeline shows what happened, but framed as a soft fallback rather
    # than a hard failure since the SQL agent will still run.
    _emit(PreflightStep(
        type="abort",
        error="Took a few rounds to scope; sending it through anyway.",
        output={"kind": "round_limit", "rounds": max_rounds},
    ))
    verdict.status = "ready"
    verdict.intent = user_prompt
    verdict.error = "round_limit"
    return verdict
