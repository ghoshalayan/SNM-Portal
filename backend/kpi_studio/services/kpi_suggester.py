"""KPI suggester — Phase J: AI proposes a set of useful KPIs for a
given source table.

Given a table from the schema introspection snapshot, the LLM is asked
to return a list of complete ``BuilderSpec`` JSON objects covering
common analytics patterns (totals, trends, top-N breakdowns,
distributions). Each proposal is validated through the spec compiler
before being returned — broken specs are dropped, so the caller
always gets a list of save-ready entries.

This is a single-shot LLM call (no tool-use loop) — the schema is
small enough to fit in context and we don't need the model to drill
into individual values. Failure modes mirror ``insight_generator``:
provider errors and parse errors degrade silently to an empty list
so the editor still works.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError,
)
from kpi_studio.schemas import BuilderSpec, ChartConfig, SchemaPayload, TableInfo
from kpi_studio.services.spec_compiler import SpecCompileError, compile_spec

log = logging.getLogger(__name__)


# Caps — keep the prompt small so the LLM can spend tokens on
# generating diverse suggestions rather than re-reading a giant schema.
_MAX_TABLES_IN_CONTEXT = 12
_MAX_COLUMNS_PER_TABLE = 30


_SYSTEM_PROMPT = """\
You are a BI analyst who designs Power BI–style dashboards. Given a
target table and its column types, propose a *diverse* set of useful
KPIs covering different analytical angles:

  * a headline TOTAL or COUNT (scorecard)
  * a TIME TREND if a date/time column exists (line chart)
  * a TOP-N breakdown by a categorical column (bar chart, top_n=10)
  * a DISTRIBUTION across a categorical column (pie chart, when 3-7
    distinct values are likely)
  * a STAT_GROUP combining 3-4 related aggregates from the same table
  * a DETAIL TABLE showing the most useful raw columns

Each proposal MUST be a valid BuilderSpec JSON. The exact schema:

  {
    "name": "<short business-friendly title>",
    "description": "<one sentence explaining what this measures>",
    "builder_spec": {
      "chart_type": "scorecard" | "stat_group" | "bar" | "pie" | "line" | "table",
      "source": { "kind": "table", "schema": "<schema or null>", "name": "<table>" },
      "wells": {
        // depends on chart_type:
        // scorecard -> { "value": [{ "column": "...", "agg": "SUM"|"COUNT"|... }] }
        // stat_group -> { "values": [{ "column": "...", "agg": "..." }, ...] }
        // bar / pie -> { "axis": [{ "column": "..." }], "values": [{ "column": "...", "agg": "..." }] }
        // line -> { "axis": [{ "column": "<date col>" }], "values": [{ "column": "...", "agg": "..." }] }
        // table -> { "columns": [{ "column": "..." }, ...] }
      },
      "filters": [],
      "top_n": <int or null>,
      "time_column": "<a date/datetime col on the source, or null>"
    }
  }

Rules (strict):
1. Every column you reference must exist on the target table.
2. Only use ``SUM`` / ``AVG`` / ``MIN`` / ``MAX`` on numeric columns.
   Use ``COUNT`` / ``COUNT_DISTINCT`` on any column.
3. Bar / pie / line: axis MUST be raw (no agg), values MUST have agg.
4. Table: columns MUST be raw.
5. Use ``top_n`` (5-10) on bar charts so they don't render hundreds of
   rows.
6. Set ``time_column`` to a date-like column when the table has one,
   so the dashboard's period filter works on the KPI.
7. Pick aggregations + columns that make business sense — don't COUNT
   a primary key when SUM(amount) tells a richer story.
8. Respond with ONE JSON object: { "kpis": [ {name, description,
   builder_spec}, ... ] }. No prose, no code fences, no extra keys.
"""


@dataclass
class SuggestedKpi:
    """One ready-to-save proposal."""
    name: str
    description: str
    builder_spec: BuilderSpec
    chart_config: ChartConfig
    sql: str  # compiled, for preview


@dataclass
class SuggestionResult:
    items: List[SuggestedKpi] = field(default_factory=list)
    tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    error: Optional[str] = None


def suggest_kpis(
    *,
    provider: LlmProvider,
    schema: SchemaPayload,
    table_name: str,
    table_schema: Optional[str] = None,
    count: int = 6,
    max_tokens: int = 4000,
) -> SuggestionResult:
    """Ask the LLM for ``count`` KPI proposals for the named table.
    Always returns a ``SuggestionResult`` — the ``items`` list may be
    empty when the model fails or every proposal fails to compile."""
    target = _find_table(schema, table_schema, table_name)
    if target is None:
        return SuggestionResult(error=f"Table not found: {table_name!r}")

    payload = _build_user_payload(schema, target, count)
    messages = [
        LlmMessage(role="system", content=_SYSTEM_PROMPT),
        LlmMessage(role="user", content=payload),
    ]

    started = time.perf_counter()
    try:
        completion = provider.complete(
            messages,
            json_mode=True,
            max_tokens=max_tokens,
            temperature=0.4,
        )
    except LlmProviderError as exc:
        log.warning("kpi_studio.suggester: provider error: %s", exc)
        return SuggestionResult(
            error=f"provider_error: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    parsed = _parse_response(completion.text)
    if parsed is None:
        log.info("kpi_studio.suggester: model returned non-JSON: %r", completion.text[:300])
        return SuggestionResult(
            error="parse_error",
            tokens=int(completion.usage.get("total_tokens") or 0),
            latency_ms=completion.latency_ms,
            model=completion.model,
        )

    items: List[SuggestedKpi] = []
    for raw in parsed:
        validated = _validate_proposal(raw)
        if validated is not None:
            items.append(validated)

    return SuggestionResult(
        items=items,
        tokens=int(completion.usage.get("total_tokens") or 0),
        latency_ms=completion.latency_ms,
        model=completion.model,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_table(
    schema: SchemaPayload, schema_name: Optional[str], table_name: str,
) -> Optional[TableInfo]:
    for t in schema.tables:
        if t.name != table_name:
            continue
        if schema_name and (t.schema_name or "") != schema_name:
            continue
        return t
    return None


def _build_user_payload(
    schema: SchemaPayload, target: TableInfo, count: int,
) -> str:
    """Assemble a compact, deterministic prompt. Same input always
    yields the same payload so suggestions are reproducible across
    runs (the LLM still varies its wording at temperature=0.4, but
    the *available facts* don't drift)."""
    target_view = {
        "schema": target.schema_name,
        "name": target.name,
        "columns": [
            {"name": c.name, "type": c.type, "nullable": c.nullable,
             "primary_key": c.primary_key}
            for c in target.columns[:_MAX_COLUMNS_PER_TABLE]
        ],
        "primary_key": target.primary_key,
        "row_count_estimate": target.row_count_estimate,
    }

    # Include a handful of related tables so the model can reference
    # names that exist (the spec compiler rejects unknowns at compile
    # time, but giving the model the right vocabulary up-front is
    # cheaper than rejecting + retrying).
    related: list[dict] = []
    for t in schema.tables[:_MAX_TABLES_IN_CONTEXT]:
        if t.name == target.name:
            continue
        related.append({
            "schema": t.schema_name,
            "name": t.name,
            "column_count": len(t.columns),
        })

    body = {
        "target_table": target_view,
        "available_tables": related,
        "wanted_count": count,
        "dialect": schema.dialect,
    }
    return json.dumps(body, default=str, ensure_ascii=False)


def _parse_response(text: str) -> Optional[list]:
    """Best-effort JSON parse. Strip ```json fences if the model
    snuck them in despite the instruction."""
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        return None
    if isinstance(out, dict) and isinstance(out.get("kpis"), list):
        return out["kpis"]
    if isinstance(out, list):  # tolerate a bare array
        return out
    return None


def _validate_proposal(raw: Any) -> Optional[SuggestedKpi]:
    """Coerce one proposal dict → SuggestedKpi, dropping anything that
    doesn't compile cleanly. The spec compiler is the source of truth
    for what's valid, so we get free defence-in-depth here."""
    if not isinstance(raw, dict):
        return None
    name = (raw.get("name") or "").strip()
    description = (raw.get("description") or "").strip()
    spec_dict = raw.get("builder_spec")
    if not name or not isinstance(spec_dict, dict):
        return None

    try:
        spec = BuilderSpec.model_validate(spec_dict)
    except Exception as exc:
        log.info("kpi_studio.suggester: spec parse failed: %s", exc)
        return None

    try:
        compiled = compile_spec(spec)
    except SpecCompileError as exc:
        log.info("kpi_studio.suggester: compile failed for %r: %s", name, exc)
        return None

    return SuggestedKpi(
        name=name[:200],
        description=description[:1000],
        builder_spec=spec,
        chart_config=compiled.chart_config,
        sql=compiled.sql,
    )


__all__ = [
    "SuggestedKpi",
    "SuggestionResult",
    "suggest_kpis",
]
