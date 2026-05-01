"""LLM provider abstraction for KPI Studio.

Phase A3 ships:
  * ``LlmProvider`` protocol (this package)
  * ``OpenAICompatibleProvider`` — covers OpenAI, Cerebras, Ollama Cloud
    via the same Chat Completions interface with different base_url/key.
  * ``build_provider_from_env`` factory that reads ``KPI_*`` env vars and
    returns the right impl (or ``None`` when no key is configured —
    LLM features then degrade silently).

Phases A3+ will add:
  * Azure OpenAI (different URL pattern + auth header)
  * Microsoft Foundry (azure-ai-inference SDK)
  * Google Gemini (google-generativeai SDK)
"""
from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError, LlmResult,
    LlmTool, LlmToolCall, LlmToolResult,
)
from kpi_studio.providers.llm.factory import build_provider_from_env
from kpi_studio.providers.llm.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "LlmMessage",
    "LlmProvider",
    "LlmProviderError",
    "LlmResult",
    "LlmTool",
    "LlmToolCall",
    "LlmToolResult",
    "OpenAICompatibleProvider",
    "build_provider_from_env",
]
