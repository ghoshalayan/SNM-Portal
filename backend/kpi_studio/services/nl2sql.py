"""Natural-language → SQL via the configured LLM provider.

Single-shot generation for Phase A3:
  prompt + schema context  →  LLM  →  { sql, explanation }  →  validator

The validator runs *before* the response goes back to the user so the
editor can warn about safety violations without an extra round-trip.
The user is always shown the raw SQL and decides whether to run it.

This module does not execute SQL — execution stays in
``services/executor.py``.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError,
)
from kpi_studio.services.schema_context import build_schema_context
from kpi_studio.services.sql_safety import (
    SafeQuery, SqlSafetyError, validate_select_query,
)
from kpi_studio.schemas import SchemaPayload

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You write {dialect} SELECT queries for a read-only analytics tool.

Rules (strict):
1. Output **only** a JSON object: {{"sql": "...", "explanation": "..."}}
2. The SQL must be a single SELECT statement. No DDL, DML, or system tables.
3. Reference only tables and columns that appear in the schema below.
4. Prefer explicit JOINs over subqueries when both work.
5. If the user's question cannot be answered from the schema, return
   {{"sql": "", "explanation": "Cannot answer — <reason>"}} instead of guessing.
6. Keep the explanation to 1-3 sentences in plain English.

Schema:
{schema}
"""


@dataclass
class Nl2SqlResult:
    sql: str
    """Generated SQL — may be empty if the model declined to answer."""

    explanation: str
    """Plain-English summary of what the SQL does (or why it couldn't)."""

    provider: str
    model: str
    latency_ms: int
    usage: dict

    safety: Optional[SafeQuery] = None
    """Result of validating the generated SQL. ``None`` when ``sql`` is empty."""

    safety_error: Optional[str] = None
    """Validator error message when validation fails. Lets the UI surface
    a warning while still showing the generated SQL for the user to fix."""

    safety_findings: list[str] = None  # type: ignore[assignment]


def generate_sql(
    *,
    provider: LlmProvider,
    schema: SchemaPayload,
    user_prompt: str,
    dialect: str = "T-SQL",
    max_tokens: int = 800,
) -> Nl2SqlResult:
    """Run one NL→SQL turn. Raises ``LlmProviderError`` on provider failure.

    Validation outcomes are returned as fields on the result, not raised —
    a validator failure shouldn't void a useful generation; the user can
    edit the SQL and try again.
    """
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        raise ValueError("user_prompt is required")

    schema_text = build_schema_context(schema)
    system_prompt = _SYSTEM_PROMPT.format(dialect=dialect, schema=schema_text)

    messages = [
        LlmMessage(role="system", content=system_prompt),
        LlmMessage(role="user", content=user_prompt),
    ]

    result = provider.complete(
        messages,
        json_mode=True,
        max_tokens=max_tokens,
        temperature=0.1,
    )

    parsed = _parse_json_response(result.text)
    sql = (parsed.get("sql") or "").strip()
    explanation = (parsed.get("explanation") or "").strip()

    safe: Optional[SafeQuery] = None
    safety_error: Optional[str] = None
    findings: list[str] = []

    if sql:
        safe_dialect = "tsql" if dialect.lower().replace("-", "") in ("tsql", "mssql") else dialect.lower()
        try:
            safe = validate_select_query(sql, dialect=safe_dialect)
        except SqlSafetyError as exc:
            safety_error = str(exc)
            findings = list(getattr(exc, "findings", []) or [])
            log.info(
                "kpi_studio.nl2sql: validation failed for generated SQL: %s",
                safety_error,
            )

    return Nl2SqlResult(
        sql=sql,
        explanation=explanation,
        provider=provider.name,
        model=result.model,
        latency_ms=result.latency_ms,
        usage=dict(result.usage),
        safety=safe,
        safety_error=safety_error,
        safety_findings=findings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict:
    """Tolerant JSON parser — providers occasionally wrap the JSON in a
    ```json fence, prepend an explanation, etc. We strip the obvious stuff
    and try once more before giving up."""
    if not text:
        return {}

    # First attempt: as-is.
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Strip ```json … ``` fences.
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            data = json.loads(fenced.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Last resort: grab the outermost {...} block.
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    raise LlmProviderError(
        "LLM did not return parseable JSON. "
        f"First 200 chars: {text[:200]!r}"
    )
