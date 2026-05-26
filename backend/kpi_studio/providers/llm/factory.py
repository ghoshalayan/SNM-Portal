"""Factory: env vars → ``LlmProvider`` instance.

The host calls this once at startup and passes the result into
``KpiStudioConfig``. Returns ``None`` when no provider is configured —
in that case LLM features (NL→SQL, chat) silently degrade and the
manual-SQL surfaces still work.

Read order is intentional: ``KPI_LLM_PROVIDER`` selects the impl;
provider-specific env vars supply the keys/URLs/models.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

from kpi_studio.providers.llm.base import LlmProvider
from kpi_studio.providers.llm.openai_compatible import OpenAICompatibleProvider

log = logging.getLogger(__name__)


# Provider name → env var prefix mapping. Each variant is OpenAI-compatible
# at the protocol level; only base_url + key + model differ.
_OPENAI_COMPAT_DEFAULTS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model_default": "gpt-4o-mini",
        "key_env": "KPI_OPENAI_API_KEY",
        "model_env": "KPI_OPENAI_MODEL",
        "base_url_env": "KPI_OPENAI_BASE_URL",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "model_default": "llama-3.3-70b",
        "key_env": "KPI_CEREBRAS_API_KEY",
        "model_env": "KPI_CEREBRAS_MODEL",
        "base_url_env": "KPI_CEREBRAS_BASE_URL",
    },
    "ollama_cloud": {
        "base_url": "https://ollama.com/v1",
        "model_default": "llama3.3",
        "key_env": "KPI_OLLAMA_CLOUD_API_KEY",
        "model_env": "KPI_OLLAMA_CLOUD_MODEL",
        "base_url_env": "KPI_OLLAMA_CLOUD_BASE_URL",
    },
    # T-901 — OpenRouter. One key, ~200 models behind ``model`` strings like
    # ``anthropic/claude-3.5-sonnet`` / ``openai/gpt-4o`` /
    # ``google/gemini-flash-1.5``. Recommends two extra HTTP headers for
    # routing fairness + analytics: ``HTTP-Referer`` and ``X-Title``.
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model_default": "anthropic/claude-3.5-sonnet",
        "key_env": "KPI_OPENROUTER_API_KEY",
        "model_env": "KPI_OPENROUTER_MODEL",
        "base_url_env": "KPI_OPENROUTER_BASE_URL",
        # Optional — surface these in extra HTTP headers when set.
        "referer_env": "KPI_OPENROUTER_REFERER",
        "app_name_env": "KPI_OPENROUTER_APP_NAME",
    },
}


def _build_openai_compat(
    selected: str,
    *,
    api_key: str,
    model: str,
    base_url: str,
    referer: Optional[str] = None,
    app_name: Optional[str] = None,
):
    """Construct an OpenAICompatibleProvider with the right extra
    headers for the chosen provider. Centralised so both the env-bootstrap
    path (``build_provider_from_env``) and the DB-settings path (used by
    ``build_provider_for_stage``) produce identical providers."""
    extras: dict[str, str] = {}
    if selected == "openrouter":
        if referer:
            extras["HTTP-Referer"] = referer
        if app_name:
            extras["X-Title"] = app_name
    return OpenAICompatibleProvider(
        api_key=api_key, model=model, base_url=base_url, name=selected,
        extra_headers=(extras or None),
    )


def build_provider_from_env(env: Optional[Mapping[str, str]] = None) -> Optional[LlmProvider]:
    """Build an LLM provider from env vars; ``None`` if disabled / unconfigured.

    Reads ``KPI_LLM_PROVIDER``. If absent or blank, returns ``None``.
    """
    env = env if env is not None else os.environ
    selected = (env.get("KPI_LLM_PROVIDER") or "").strip().lower()
    if not selected:
        return None

    if selected in _OPENAI_COMPAT_DEFAULTS:
        cfg = _OPENAI_COMPAT_DEFAULTS[selected]
        api_key = (env.get(cfg["key_env"]) or "").strip()
        if not api_key:
            log.warning(
                "kpi_studio: KPI_LLM_PROVIDER=%s but %s is empty; "
                "LLM features disabled.",
                selected, cfg["key_env"],
            )
            return None
        model = (env.get(cfg["model_env"]) or cfg["model_default"]).strip()
        base_url = (env.get(cfg["base_url_env"]) or cfg["base_url"]).strip()
        referer = (env.get(cfg.get("referer_env", "")) or "").strip() or None
        app_name = (env.get(cfg.get("app_name_env", "")) or "").strip() or None
        return _build_openai_compat(
            selected,
            api_key=api_key, model=model, base_url=base_url,
            referer=referer, app_name=app_name,
        )

    # Azure OpenAI / Foundry / Gemini land here in later phases.
    log.warning(
        "kpi_studio: KPI_LLM_PROVIDER=%s is not yet implemented; "
        "LLM features disabled.",
        selected,
    )
    return None
