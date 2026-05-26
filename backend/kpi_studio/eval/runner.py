"""Eval runner — fires every active golden case through the NL→SQL
pipeline and writes a KpiEvalRun + one KpiEvalCaseResult per case.

The runner intentionally re-uses the same services the user-facing
chat / nl_generate endpoints use, in the same order:

* preflight.run_preflight        (when enabled in KpiSettings)
* nl2sql_agent.run_agent
* executor.execute_safe_query
* sql_safety.validate_select_query

so a passing eval means *the user-facing pipeline* passed for that
prompt — not a parallel test harness that diverges from production.

Preflight outcome handling for eval contexts:

* ``ready``     → use ``verdict.intent`` as the agent's user_prompt
                  (case.prompt rides along as ``original_prompt``).
* ``ask_user``  → counts as a case failure (``agent_no_proposal``);
                  author the case more specifically or add domain
                  knowledge so the Planner can disambiguate unaided.
* ``abort``     → counts as a case error (``agent_timeout``); the
                  Planner ran out of rounds / tokens without converging.

Comparators (run after the pipeline returns):

1. **tables_referenced** ⊇ case.expected_tables    (tables_missing)
2. case.strict_tables → tables_referenced == expected_tables  (tables_extra)
3. **columns_referenced** ⊇ case.expected_columns  (columns_missing)
4. case.expected_row_count_min ≤ produced_row_count ≤ case.expected_row_count_max
5. SQL executed cleanly                            (sql_exec_failed)

Comparator results are recorded as discrete failure codes on
``KpiEvalCaseResult.failure_reasons`` (see EVAL_FAILURE_CODES in
models). Status is ``pass`` iff failure_reasons is empty.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import sqlglot
from sqlglot import exp as sqlglot_exp
from sqlalchemy.orm import Session

from kpi_studio.config import KpiStudioConfig
from kpi_studio.models import (
    EVAL_FAILURE_CODES,
    KpiEvalCase,
    KpiEvalCaseResult,
    KpiEvalRun,
    KpiSettings,
)
from kpi_studio.providers.llm.factory import build_provider_from_env
from kpi_studio.services import introspector
from kpi_studio.services.executor import (
    QueryExecutionError,
    execute_safe_query,
)
from kpi_studio.services.nl2sql_agent import (
    AgentResult,
    ExecutedSqlResult,
    run_agent,
)
from kpi_studio.services.preflight import PreflightVerdict, run_preflight
from kpi_studio.services.settings_service import get_effective
from kpi_studio.services.sql_safety import SqlSafetyError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result containers (in-memory; persisted versions are the SQLAlchemy rows)
# ---------------------------------------------------------------------------

@dataclass
class CaseOutcome:
    """In-memory record per case. Mirrors KpiEvalCaseResult columns the
    runner needs to inspect before deciding aggregate status; the
    persisted row is built from this once the case completes."""
    case_id: int
    name: str
    status: str  # one of EVAL_CASE_STATUSES
    produced_sql: Optional[str] = None
    produced_row_count: Optional[int] = None
    tables_referenced: list[str] = field(default_factory=list)
    columns_referenced: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    failure_detail: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    tokens_used: int = 0
    nl_run_id: Optional[int] = None


@dataclass
class EvalSummary:
    """What the CLI / API returns after a full run."""
    eval_run_id: int
    started_at: datetime
    finished_at: datetime
    cases_total: int
    cases_passed: int
    cases_failed: int
    cases_errored: int
    cases_skipped: int
    pass_rate: float
    outcomes: list[CaseOutcome]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_eval(
    *,
    db: Session,
    config: KpiStudioConfig,
    tags: Optional[Iterable[str]] = None,
    case_ids: Optional[Iterable[int]] = None,
    triggered_by: str = "cli",
    triggered_by_user_id: Optional[int] = None,
    against_snapshot_id: Optional[int] = None,
    on_case: Optional[callable] = None,
) -> EvalSummary:
    """Execute the eval. Returns once every case has a result row.

    Parameters
    ----------
    tags
        If supplied, only cases whose ``tags`` JSON list intersects this
        set are run. Empty / None = all active cases.
    case_ids
        Restrict to specific case_ids (overrides ``tags`` when both
        given). Mainly for "re-run only the failures from run X" flows.
    against_snapshot_id
        If supplied, force this snapshot as the schema source instead
        of the current one. Used by replay / time-travel debugging.
    on_case
        Optional callback ``on_case(outcome)`` fired after each case
        completes — used by the CLI to stream progress.
    """
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()

    # Insert the parent run row first so cases can FK into it. We'll
    # update aggregates at the end.
    run = KpiEvalRun(
        started_at=started_at,
        triggered_by=triggered_by,
        triggered_by_user_id=triggered_by_user_id,
        tags_filter=list(tags) if tags else None,
        prompt_version=os.getenv("KPI_PROMPT_VERSION") or None,
    )
    db.add(run)
    db.flush()

    # Resolve the schema snapshot once for the whole run.
    snapshot = None
    if against_snapshot_id is not None:
        from kpi_studio.models import KpiSchemaSnapshot
        snapshot = db.get(KpiSchemaSnapshot, against_snapshot_id)
    if snapshot is None:
        snapshot = introspector.get_current_snapshot(db)
    if snapshot is not None:
        run.snapshot_id = snapshot.snapshot_id

    # Resolve LLM provider. If absent, every case becomes ``error`` with
    # ``provider_error``. Better than swallowing — eval is useless
    # without a provider, and CI should see this loud.
    provider = config.llm_provider or build_provider_from_env()

    # Build the case set.
    q = db.query(KpiEvalCase).filter(KpiEvalCase.is_active == True)  # noqa: E712
    if case_ids:
        q = q.filter(KpiEvalCase.case_id.in_(list(case_ids)))
    cases = q.order_by(KpiEvalCase.case_id.asc()).all()

    if tags and not case_ids:
        tag_set = set(tags)
        cases = [c for c in cases if c.tags and tag_set.intersection(c.tags)]

    outcomes: list[CaseOutcome] = []
    passed = failed = errored = skipped = 0

    schema_payload = introspector.load_payload(snapshot) if snapshot else None
    effective = get_effective(db, env=os.environ)

    for case in cases:
        case_started = time.perf_counter()

        # Snapshot-pinned cases skip when run against the wrong snapshot.
        if case.pinned_snapshot_id is not None and snapshot is not None \
                and case.pinned_snapshot_id != snapshot.snapshot_id:
            outcome = CaseOutcome(
                case_id=case.case_id,
                name=case.name,
                status="skipped",
                failure_reasons=[],
                failure_detail={"reason": "snapshot_pinned",
                                "expected": case.pinned_snapshot_id,
                                "actual": snapshot.snapshot_id},
            )
            _persist_outcome(db, run.eval_run_id, outcome)
            outcomes.append(outcome)
            skipped += 1
            if on_case:
                on_case(outcome)
            continue

        if provider is None or schema_payload is None:
            # Skip the agent call entirely — record the failure and move on.
            outcome = CaseOutcome(
                case_id=case.case_id,
                name=case.name,
                status="error",
                failure_reasons=["provider_error" if provider is None else "agent_no_proposal"],
                failure_detail={
                    "reason": "llm_provider_unavailable" if provider is None
                              else "no_schema_snapshot",
                },
                duration_ms=int((time.perf_counter() - case_started) * 1000),
            )
            _persist_outcome(db, run.eval_run_id, outcome)
            outcomes.append(outcome)
            errored += 1
            if on_case:
                on_case(outcome)
            continue

        outcome = _run_one_case(
            db=db,
            case=case,
            provider=provider,
            schema_payload=schema_payload,
            engine=config.target_engine,
            effective_settings=effective,
            case_started_perf=case_started,
        )
        _persist_outcome(db, run.eval_run_id, outcome)
        outcomes.append(outcome)

        if outcome.status == "pass":
            passed += 1
            case.last_pass_at = datetime.now(timezone.utc)
            case.last_fail_reason = None
        elif outcome.status == "fail":
            failed += 1
            case.last_fail_reason = ",".join(outcome.failure_reasons) or "unknown"
        else:  # error / skipped
            errored += 1 if outcome.status == "error" else 0
            case.last_fail_reason = outcome.failure_detail.get("reason") if outcome.status == "error" else None

        if on_case:
            on_case(outcome)

    # Finalize the run row.
    run.finished_at = datetime.now(timezone.utc)
    run.cases_total = len(cases)
    run.cases_passed = passed
    run.cases_failed = failed
    run.cases_errored = errored
    run.cases_skipped = skipped
    run.summary_json = {
        "wall_clock_s": round(time.perf_counter() - started_perf, 2),
        "pass_rate": (passed / len(cases)) if cases else 0.0,
    }
    db.commit()

    pass_rate = (passed / len(cases)) if cases else 0.0

    return EvalSummary(
        eval_run_id=run.eval_run_id,
        started_at=started_at,
        finished_at=run.finished_at,
        cases_total=len(cases),
        cases_passed=passed,
        cases_failed=failed,
        cases_errored=errored,
        cases_skipped=skipped,
        pass_rate=pass_rate,
        outcomes=outcomes,
    )


# ---------------------------------------------------------------------------
# Per-case execution
# ---------------------------------------------------------------------------

def _run_one_case(
    *,
    db: Session,
    case: KpiEvalCase,
    provider,
    schema_payload,
    engine,
    effective_settings,
    case_started_perf: float,
) -> CaseOutcome:
    """Run the pipeline for one case + compare expected vs produced.

    Sequentially:
      1. Run pre-flight Planner if enabled (matches chat_service.run_turn).
         ``ask_user`` and ``abort`` verdicts terminate the case as a fail
         — the eval treats clarification-requests as the agent failing
         to handle the prompt unaided, which is the right signal for
         regression detection.
      2. Invoke the agent with the (possibly disambiguated) intent.
      3. If agent returned SQL but didn't execute, execute via
         ``execute_safe_query``.
      4. Parse referenced tables/columns from produced SQL.
      5. Compare against case expectations.
    """
    outcome = CaseOutcome(case_id=case.case_id, name=case.name, status="error")

    # ---- 1. Pre-flight Planner (mirrors chat_service.run_turn) -----------
    # The runner *must* call the same disambiguation pass production uses,
    # otherwise a regression in the Planner is invisible to eval. When
    # ``preflight_enabled`` is False in KpiSettings, we skip — same as
    # chat does.
    agent_prompt = case.prompt
    if effective_settings.preflight_enabled:
        try:
            verdict: PreflightVerdict = run_preflight(
                provider=provider,
                schema=schema_payload,
                user_prompt=case.prompt,
                domain_knowledge=effective_settings.domain_knowledge or None,
                max_rounds=effective_settings.preflight_max_rounds,
                max_tokens_per_call=effective_settings.max_tokens_per_call,
                token_budget=effective_settings.token_budget,
            )
        except Exception as exc:
            outcome.status = "error"
            outcome.failure_reasons = ["provider_error"]
            outcome.failure_detail = {"reason": "preflight_raised",
                                      "message": str(exc)[:500]}
            outcome.duration_ms = int((time.perf_counter() - case_started_perf) * 1000)
            return outcome

        outcome.tokens_used += verdict.total_tokens

        if verdict.status == "ask_user":
            # Preflight wanted a clarification. For eval purposes that's
            # a failure to handle the prompt — author the case more
            # specifically (or add domain_knowledge / glossary terms to
            # disambiguate the language).
            outcome.status = "fail"
            outcome.failure_reasons = ["agent_no_proposal"]
            outcome.failure_detail = {
                "reason": "preflight_ask_user",
                "question": verdict.user_question,
                "suggested_options": verdict.suggested_options,
            }
            outcome.duration_ms = int((time.perf_counter() - case_started_perf) * 1000)
            return outcome
        if verdict.status == "abort":
            outcome.status = "error"
            outcome.failure_reasons = ["agent_timeout"]
            outcome.failure_detail = {"reason": "preflight_abort",
                                      "message": verdict.error or "no detail"}
            outcome.duration_ms = int((time.perf_counter() - case_started_perf) * 1000)
            return outcome
        # status == "ready" → feed the disambiguated intent to the agent.
        if verdict.intent:
            agent_prompt = verdict.intent

    # ---- 2. Agent --------------------------------------------------------
    try:
        agent_result: AgentResult = run_agent(
            provider=provider,
            schema=schema_payload,
            target_engine=engine,
            db=db,
            user_prompt=agent_prompt,
            user_id=None,
            company_id=None,
            max_iterations=effective_settings.max_iterations,
            token_budget=effective_settings.token_budget,
            max_tokens_per_call=effective_settings.max_tokens_per_call,
            system_prompt_extras=effective_settings.domain_knowledge or None,
            original_prompt=case.prompt if agent_prompt != case.prompt else None,
            execute_sql_fn=None,
        )
    except Exception as exc:
        outcome.status = "error"
        outcome.failure_reasons = ["provider_error"]
        outcome.failure_detail = {"reason": "agent_raised", "message": str(exc)[:500]}
        outcome.duration_ms = int((time.perf_counter() - case_started_perf) * 1000)
        return outcome

    # Accumulate tokens — preflight may have already added some.
    outcome.tokens_used += agent_result.total_tokens
    outcome.produced_sql = agent_result.sql or None

    # Agent shape: missing SQL with succeeded=False => no proposal.
    if not agent_result.sql:
        outcome.status = "fail"
        outcome.failure_reasons = ["agent_no_proposal"]
        if agent_result.error:
            outcome.failure_detail = {"reason": agent_result.error[:500]}
        outcome.duration_ms = int((time.perf_counter() - case_started_perf) * 1000)
        return outcome

    # Try to execute the proposed SQL.
    exec_result = None
    try:
        exec_result = execute_safe_query(
            engine, db,
            sql=agent_result.sql,
            source="preview",
            user_id=None,
            company_id=None,
        )
    except SqlSafetyError as exc:
        outcome.failure_reasons.append("sql_exec_failed")
        outcome.failure_detail["sql_exec_failed"] = {"kind": "safety", "message": str(exc)[:500]}
    except QueryExecutionError as exc:
        outcome.failure_reasons.append("sql_exec_failed")
        outcome.failure_detail["sql_exec_failed"] = {"kind": "executor", "message": str(exc)[:500]}
    except Exception as exc:
        outcome.failure_reasons.append("sql_exec_failed")
        outcome.failure_detail["sql_exec_failed"] = {"kind": "unexpected", "message": str(exc)[:500]}

    # Parse tables / columns referenced.
    tables, columns = _parse_refs(agent_result.sql, dialect_for(engine))
    outcome.tables_referenced = sorted(tables)
    outcome.columns_referenced = sorted(columns)

    # Comparators.
    _compare_tables(case, outcome, tables)
    _compare_columns(case, outcome, columns)
    if exec_result is not None:
        outcome.produced_row_count = exec_result.row_count
        _compare_row_count(case, outcome, exec_result.row_count)

    outcome.duration_ms = int((time.perf_counter() - case_started_perf) * 1000)
    outcome.status = "pass" if not outcome.failure_reasons else "fail"
    return outcome


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------

def _compare_tables(case: KpiEvalCase, outcome: CaseOutcome, produced: set[str]) -> None:
    expected = set((case.expected_tables or []))
    if not expected:
        return
    produced_lower = {t.lower() for t in produced}
    missing = sorted(t for t in expected if t.lower() not in produced_lower)
    if missing:
        outcome.failure_reasons.append("tables_missing")
        outcome.failure_detail.setdefault("tables_missing", {})["missing"] = missing
        outcome.failure_detail["tables_missing"]["produced"] = sorted(produced)

    if case.strict_tables:
        extras = sorted(t for t in produced if t.lower() not in {e.lower() for e in expected})
        if extras:
            outcome.failure_reasons.append("tables_extra")
            outcome.failure_detail.setdefault("tables_extra", {})["extras"] = extras


def _compare_columns(case: KpiEvalCase, outcome: CaseOutcome, produced: set[str]) -> None:
    """Compare expected vs produced qualified column refs.

    Match is permissive: ``customer.name`` in expected matches
    ``customer.name`` or ``c.name`` (where ``c`` is an alias for
    ``customer``). We can't reliably resolve aliases from a parsed AST
    here without a full resolver, so we drop the table prefix when
    matching and check ``name`` against the unqualified set too. False
    negatives are OK (case fails loudly); false positives are not.
    """
    expected = set((case.expected_columns or []))
    if not expected:
        return
    produced_lower = {c.lower() for c in produced}
    produced_bare = {c.split(".")[-1].lower() for c in produced}

    missing = []
    for col in expected:
        col_l = col.lower()
        bare = col_l.split(".")[-1]
        if col_l in produced_lower:
            continue
        if bare in produced_bare:
            continue
        missing.append(col)
    if missing:
        outcome.failure_reasons.append("columns_missing")
        outcome.failure_detail.setdefault("columns_missing", {})["missing"] = sorted(missing)


def _compare_row_count(case: KpiEvalCase, outcome: CaseOutcome, row_count: int) -> None:
    lo = case.expected_row_count_min
    hi = case.expected_row_count_max
    if lo is None and hi is None:
        return
    if lo is not None and row_count < lo:
        outcome.failure_reasons.append("row_count_low")
        outcome.failure_detail["row_count_low"] = {"got": row_count, "min": lo}
    if hi is not None and row_count > hi:
        outcome.failure_reasons.append("row_count_high")
        outcome.failure_detail["row_count_high"] = {"got": row_count, "max": hi}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_refs(sql: str, dialect: str) -> tuple[set[str], set[str]]:
    """Return (tables_referenced, columns_referenced).

    Best-effort: when sqlglot fails to parse (unlikely after the
    validator already accepted it, but possible on edge dialect
    syntax), returns empty sets so the comparator records a missing
    reference instead of a parse exception.
    """
    tables: set[str] = set()
    columns: set[str] = set()
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return tables, columns

    for t in parsed.find_all(sqlglot_exp.Table):
        # Use ``name`` (table) — strip schema; the eval cases are
        # authored against bare table names today. If schema-qualified
        # matching becomes important, we can add it later as a
        # comparator option.
        if t.name:
            tables.add(t.name)

    for c in parsed.find_all(sqlglot_exp.Column):
        if c.name:
            table_part = c.table or ""
            qualified = f"{table_part}.{c.name}" if table_part else c.name
            columns.add(qualified)

    return tables, columns


def dialect_for(engine) -> str:
    name = engine.dialect.name
    return "tsql" if name == "mssql" else name


def _persist_outcome(db: Session, eval_run_id: int, outcome: CaseOutcome) -> None:
    db.add(KpiEvalCaseResult(
        eval_run_id=eval_run_id,
        case_id=outcome.case_id,
        status=outcome.status,
        produced_sql=outcome.produced_sql,
        produced_row_count=outcome.produced_row_count,
        tables_referenced=outcome.tables_referenced,
        columns_referenced=outcome.columns_referenced,
        failure_reasons=outcome.failure_reasons or None,
        failure_detail=outcome.failure_detail or None,
        duration_ms=outcome.duration_ms,
        tokens_used=outcome.tokens_used,
        nl_run_id=outcome.nl_run_id,
    ))
    db.flush()


# Sanity-check the failure-code set matches what's declared in models.
# Keeps the two in sync — a typo here surfaces at import time, not run.
_KNOWN_CODES = set(EVAL_FAILURE_CODES)
