"""LLM provider protocol — narrow on purpose.

Two methods:
  * ``complete(messages, json_mode=...)`` — single-shot text completion (A3)
  * ``complete_with_tools(messages, tools, ...)`` — one round-trip of an
    agentic loop (A7); the model either returns text or a list of tool
    calls that the caller (orchestrator) executes and feeds back.

Each provider implementation handles its own SDK quirks; the orchestrator
stays SDK-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Protocol, Sequence

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class LlmMessage:
    role: Role
    content: str
    # Tool-use shapes (Phase A7). Populated only on assistant turns that
    # request tool calls, and on tool-result turns the orchestrator appends.
    tool_calls: Optional[list["LlmToolCall"]] = None
    tool_call_id: Optional[str] = None  # set on role="tool" replies


@dataclass
class LlmToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LlmTool:
    """Schema describing a tool the model can call.

    ``parameters`` is a JSON-Schema dict; OpenAI passes it straight through
    in the function-calling API. Other providers may need to translate.
    """
    name: str
    description: str
    parameters: dict


@dataclass
class LlmResult:
    text: str
    """The assistant's response content, post-trim."""

    model: str
    """Identifier echoed by the provider — handy for audit logs."""

    latency_ms: int
    """Wall-clock time for the call, including network."""

    usage: dict = field(default_factory=dict)
    """Provider-reported token counts (best-effort; may be empty)."""


@dataclass
class LlmToolResult:
    """Outcome of one ``complete_with_tools`` round-trip.

    Either ``tool_calls`` is non-empty (model wants to invoke tools — the
    orchestrator runs them and appends results to messages), or
    ``content`` carries final text and the loop should terminate.

    ``raw_assistant_message`` is the assistant turn the orchestrator must
    append to message history before sending tool results back.
    Stashed-as-dict so each provider can keep its own SDK quirks.
    """
    tool_calls: list[LlmToolCall]
    content: str
    raw_assistant_message: dict
    model: str
    latency_ms: int
    usage: dict = field(default_factory=dict)


class LlmProviderError(RuntimeError):
    """Raised on provider-side failures (HTTP error, malformed response,
    timeout). The endpoint layer catches this and returns a clean 502/504."""


class LlmProvider(Protocol):
    """Minimum surface every provider must implement.

    ``json_mode`` requests a JSON-only response (provider-specific support;
    we always defensively parse the result so behaviour is consistent even
    when the provider can't natively enforce it).
    """

    name: str

    def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LlmResult:
        ...

    def complete_with_tools(
        self,
        messages: Sequence[LlmMessage],
        tools: Sequence[LlmTool],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LlmToolResult:
        """One round-trip of the tool-use loop.

        The model either calls tools (return value has ``tool_calls`` set)
        or replies with text (``content`` set). The orchestrator drives
        the loop; the provider just round-trips one turn.
        """
        ...
