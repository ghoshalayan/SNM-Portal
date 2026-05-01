"""Insight generator — second LLM pass that reads an executed result
and produces a short narrative + a list of follow-up recommendations.

This runs *after* SQL execution succeeds. It deliberately does NOT use
tool-use — the model only sees the result rows, the SQL, the user's
prompt, and the chart type, and must respond with strict JSON.

Failure modes:
  * Provider error → returns ``InsightResult(error=...)`` and the
    chat turn continues; the assistant message is saved without insight.
  * JSON parse failure → same; we never block the user-visible answer
    on the analyser.

Token budget is held in check by capping the number of rows + cells we
serialise into the prompt (a 200k-row result would otherwise blow the
context window).
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

log = logging.getLogger(__name__)


# Caps on what we ship into the prompt. Insight quality plateaus quickly
# beyond a few rows of representative data; we'd rather spend tokens on
# the response than on a giant table the model will only sample.
_MAX_ROWS = 30
_MAX_COLUMNS = 20
_MAX_CELL_CHARS = 200

_SYSTEM_PROMPT = """\
You are a senior analyst summarising a SQL query result for a non-technical
business user. You receive the user's question, the SQL that ran, the
chart chosen, and the actual result rows.

Respond with JSON only, matching this exact shape:
  {
    "narrative": "<2-4 sentence plain-English summary of what the data shows>",
    "recommendations": [
      "<actionable follow-up 1>",
      "<actionable follow-up 2>"
    ]
  }

Rules:
  * narrative: highlight the headline number, the trend, or the outlier.
    No filler ("This data shows..."). Quote actual values when useful.
  * recommendations: 2-4 short, concrete next-steps — questions to
    investigate, segments to drill into, KPIs to compare against.
    Each item under 120 characters. Empty list is allowed when no
    follow-up is obvious.
  * If the result is empty (zero rows), narrative explains why no
    matches and recommendations propose looser filters.
  * No prose outside the JSON object. No code fences. No ``json`` prefix.
"""


@dataclass
class InsightResult:
    narrative: str = ""
    recommendations: List[str] = field(default_factory=list)
    tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    error: Optional[str] = None


def generate_insight(
    *,
    provider: LlmProvider,
    user_prompt: str,
    sql: str,
    columns: List[str],
    rows: List[List[Any]],
    chart_type: Optional[str] = None,
    max_tokens: int = 600,
) -> InsightResult:
    """Run the insight pass. Always returns an ``InsightResult`` —
    callers should check ``error`` and treat as optional UI sugar."""
    payload = _build_user_payload(
        user_prompt=user_prompt, sql=sql,
        columns=columns, rows=rows, chart_type=chart_type,
    )
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
            temperature=0.3,
        )
    except LlmProviderError as exc:
        log.warning("kpi_studio.insight: provider error: %s", exc)
        return InsightResult(
            error=f"provider_error: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    parsed = _parse_json(completion.text)
    if parsed is None:
        log.info("kpi_studio.insight: model returned non-JSON: %r", completion.text[:200])
        return InsightResult(
            error="parse_error",
            tokens=int(completion.usage.get("total_tokens") or 0),
            latency_ms=completion.latency_ms,
            model=completion.model,
        )

    return InsightResult(
        narrative=_clean_str(parsed.get("narrative")),
        recommendations=_clean_recommendations(parsed.get("recommendations")),
        tokens=int(completion.usage.get("total_tokens") or 0),
        latency_ms=completion.latency_ms,
        model=completion.model,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_user_payload(
    *,
    user_prompt: str,
    sql: str,
    columns: List[str],
    rows: List[List[Any]],
    chart_type: Optional[str],
) -> str:
    """Assemble a compact, deterministic prompt — same input always
    yields the same payload so the result is reproducible across runs."""
    cols = list(columns or [])[:_MAX_COLUMNS]
    truncated_rows = []
    for row in (rows or [])[:_MAX_ROWS]:
        truncated_rows.append([_truncate_cell(v) for v in list(row)[:_MAX_COLUMNS]])

    body: dict[str, Any] = {
        "user_question": (user_prompt or "").strip(),
        "sql": (sql or "").strip(),
        "chart_type": chart_type or "table",
        "result": {
            "columns": cols,
            "rows": truncated_rows,
            "row_count": len(rows or []),
            "shown_rows": len(truncated_rows),
        },
    }
    return json.dumps(body, default=str, ensure_ascii=False)


def _truncate_cell(value: Any) -> Any:
    """Clip very long cell values so a single CLOB doesn't blow the
    prompt budget. Numbers and ``None`` pass through unchanged."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    s = str(value)
    if len(s) > _MAX_CELL_CHARS:
        return s[: _MAX_CELL_CHARS - 1] + "…"
    return s


def _parse_json(text: str) -> Optional[dict]:
    """Best-effort JSON parse. Some providers wrap the response in
    ```json ... ``` fences even when asked not to — strip those before
    parsing. Returns ``None`` on irrecoverable garbage."""
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
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    # Cap narrative length defensively — UI breaks on multi-page text.
    return s[:2000]


def _clean_recommendations(value: Any) -> List[str]:
    """Normalise to a list of trimmed strings, drop empties, cap count."""
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value[:6]:
        if isinstance(item, str):
            s = item.strip()
        elif isinstance(item, dict):
            # Some models wrap each rec as {"text": "..."} — accept it.
            s = str(item.get("text") or item.get("recommendation") or "").strip()
        else:
            s = str(item).strip()
        if s:
            out.append(s[:200])
    return out
