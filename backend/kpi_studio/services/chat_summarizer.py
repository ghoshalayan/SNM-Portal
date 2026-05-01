"""Rolling-summary compactor — keeps long sessions cheap.

A chat session can grow indefinitely. To keep prompt size flat we:
  * keep the most recent ``KEEP_LAST_PAIRS`` Q&A pairs as raw history
  * compress everything before that into a single ``rolling_summary``
    paragraph stored on the ``KpiChatSession`` row

The summary is regenerated incrementally — each time we cross another
``COMPACT_EVERY_PAIRS`` boundary, we feed the existing summary plus the
newly-aged messages back through the LLM to extend it.

Failure modes degrade silently — a failed summarisation just leaves the
existing summary in place; the chat keeps working with the fuller raw
history fallback (paid for in tokens but visible in correctness).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

from kpi_studio.models import KpiChatMessage
from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError,
)

log = logging.getLogger(__name__)


# Tunables — keep them top-level so callers and tests can shadow.
KEEP_LAST_PAIRS = 2
"""Q&A pairs (= 2 messages each) preserved verbatim, never summarised."""

COMPACT_EVERY_PAIRS = 3
"""How many *new* completed pairs trigger a re-compaction."""

_MAX_MESSAGE_CHARS = 1200
"""Per-message clip when feeding history into the summariser."""


_SYSTEM_PROMPT = """\
You maintain a running summary of a conversation between a business user
and a SQL analytics assistant. Each turn the user asks a question and the
assistant answers using SQL on a company database.

Given the prior summary (may be empty) and the new messages, produce an
updated summary in 4-8 sentences that captures:
  * the topics the user has explored (entities, time ranges, segments)
  * the key findings or numbers surfaced so far
  * any constraints / preferences the user has stated

Stay under 800 characters. Plain prose. No bullets, no headers, no JSON.
The next turn will re-use this summary so it must read as a coherent
paragraph for an analyst joining the thread mid-stream.
"""


@dataclass
class SummaryResult:
    text: str = ""
    tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    error: Optional[str] = None


def should_compact(messages: Sequence[KpiChatMessage]) -> bool:
    """Return True when the session has accumulated enough new pairs to
    warrant a re-compaction.

    Counts only completed pairs (one user + one assistant). The first
    ``KEEP_LAST_PAIRS`` we always preserve verbatim; we only start
    summarising when there are at least ``COMPACT_EVERY_PAIRS`` *more*
    on top of those.
    """
    pair_count = _count_pairs(messages)
    return pair_count >= (KEEP_LAST_PAIRS + COMPACT_EVERY_PAIRS)


def split_for_compaction(
    messages: Sequence[KpiChatMessage],
) -> tuple[List[KpiChatMessage], List[KpiChatMessage]]:
    """Split ``messages`` into ``(to_summarise, to_keep)`` such that
    ``to_keep`` holds the most recent ``KEEP_LAST_PAIRS`` complete pairs
    (plus any trailing partial turn — typically nothing here since we
    only compact after a complete turn lands)."""
    keep_msg_target = KEEP_LAST_PAIRS * 2
    if len(messages) <= keep_msg_target:
        return [], list(messages)
    cut = len(messages) - keep_msg_target
    return list(messages[:cut]), list(messages[cut:])


def compact_summary(
    *,
    provider: LlmProvider,
    prior_summary: Optional[str],
    new_messages: Sequence[KpiChatMessage],
    max_tokens: int = 500,
) -> SummaryResult:
    """Produce an updated rolling summary. Returns an empty
    ``SummaryResult.text`` on any failure — caller should keep the
    prior summary in that case."""
    if not new_messages:
        return SummaryResult(text=(prior_summary or ""))

    payload = _build_user_payload(prior_summary, new_messages)
    messages = [
        LlmMessage(role="system", content=_SYSTEM_PROMPT),
        LlmMessage(role="user", content=payload),
    ]

    started = time.perf_counter()
    try:
        completion = provider.complete(
            messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
    except LlmProviderError as exc:
        log.warning("kpi_studio.summarizer: provider error: %s", exc)
        return SummaryResult(
            error=f"provider_error: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    text = (completion.text or "").strip()
    if not text:
        return SummaryResult(
            error="empty_response",
            tokens=int(completion.usage.get("total_tokens") or 0),
            latency_ms=completion.latency_ms,
            model=completion.model,
        )

    return SummaryResult(
        text=text[:1500],  # hard cap to defend against runaway responses
        tokens=int(completion.usage.get("total_tokens") or 0),
        latency_ms=completion.latency_ms,
        model=completion.model,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_pairs(messages: Sequence[KpiChatMessage]) -> int:
    """Count completed (user, assistant) adjacency pairs in chronological
    order. A trailing user turn without an assistant reply doesn't count."""
    pairs = 0
    i = 0
    while i < len(messages) - 1:
        if messages[i].role == "user" and messages[i + 1].role == "assistant":
            pairs += 1
            i += 2
        else:
            i += 1
    return pairs


def _build_user_payload(
    prior_summary: Optional[str],
    new_messages: Sequence[KpiChatMessage],
) -> str:
    lines: list[str] = []
    if prior_summary:
        lines.append("PRIOR SUMMARY:")
        lines.append(prior_summary.strip())
        lines.append("")
    lines.append("NEW MESSAGES:")
    for m in new_messages:
        body = (m.content or "").strip()
        if len(body) > _MAX_MESSAGE_CHARS:
            body = body[: _MAX_MESSAGE_CHARS - 1] + "…"
        # Add a tiny tail with the SQL or insight headline so the
        # summary reflects what was actually answered, not just the
        # assistant's narration.
        if m.role == "assistant" and m.insight:
            tail = (m.insight or "").strip()
            if len(tail) > 240:
                tail = tail[:239] + "…"
            body = (body + ("\n[finding] " + tail)).strip()
        lines.append(f"{m.role.upper()}: {body}")
    return "\n".join(lines)
