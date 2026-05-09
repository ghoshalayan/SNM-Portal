"""Runtime-editable settings: DB → env → default resolution.

Single global ``KpiSettings`` row. When a column is non-null, it
overrides the matching ``KPI_*`` env var. When it's null, we fall back
to the env, then to the agent's compile-time defaults.

The API key field is special: ``GET`` never returns it, only a boolean.
Updates use a sentinel (``KEEP_API_KEY``) to distinguish "no change"
from "set to empty string".
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from kpi_studio.models import KpiSettings
from kpi_studio.providers.llm.base import LlmProvider
from kpi_studio.providers.llm.openai_compatible import OpenAICompatibleProvider
from kpi_studio.schemas import KEEP_API_KEY, SettingsUpdate
from kpi_studio.services.nl2sql_agent import (
    DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_TOKENS_PER_CALL, DEFAULT_TOKEN_BUDGET,
)


# Same defaults as the OpenAI-compatible factory uses when env vars are
# unset. Duplicated here so we don't have to import the private dict.
_OPENAI_DEFAULTS = {
    "openai": {
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "key_env": "KPI_OPENAI_API_KEY",
        "model_env": "KPI_OPENAI_MODEL",
        "base_url_env": "KPI_OPENAI_BASE_URL",
    },
    "cerebras": {
        "model": "llama-3.3-70b",
        "base_url": "https://api.cerebras.ai/v1",
        "key_env": "KPI_CEREBRAS_API_KEY",
        "model_env": "KPI_CEREBRAS_MODEL",
        "base_url_env": "KPI_CEREBRAS_BASE_URL",
    },
    "ollama_cloud": {
        "model": "llama3.3",
        "base_url": "https://ollama.com/v1",
        "key_env": "KPI_OLLAMA_CLOUD_API_KEY",
        "model_env": "KPI_OLLAMA_CLOUD_MODEL",
        "base_url_env": "KPI_OLLAMA_CLOUD_BASE_URL",
    },
}


@dataclass
class EffectiveSettings:
    """The merged config the agent actually uses on a given request.

    ``provider`` is None when no source supplied an API key — the
    chatbot / agent then disables itself.
    """
    provider: Optional[LlmProvider]
    provider_name: Optional[str]
    model: Optional[str]
    has_key: bool
    using_env_fallback: bool
    token_budget: int
    max_iterations: int
    max_tokens_per_call: int
    # System Knowledge Hub — admin-curated context appended to the
    # agent's system prompt. ``None`` means no extras block.
    domain_knowledge: Optional[str] = None
    # Pre-flight Planner ↔ Resolver loop knobs (resolved with defaults
    # so chat_service can call them without null-checking each one).
    preflight_enabled: bool = True
    preflight_max_rounds: int = 5
    preflight_user_escalations: int = 2
    # Phase B2 — how many of the most recent (user, assistant) message
    # pairs to feed back into the agent on each chat turn so it can
    # follow up "now group that by region" / "and only for last
    # quarter". 0 disables threading entirely. Resolved env-only for
    # now; KpiSettings DB column can be added later if admins want a
    # UI toggle.
    chat_history_turns: int = 3


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def get_row(db: Session) -> Optional[KpiSettings]:
    """Return the singleton row or ``None`` if it doesn't exist yet."""
    return db.query(KpiSettings).order_by(KpiSettings.settings_id.asc()).first()


def update_row(
    db: Session, payload: SettingsUpdate, *, updated_by: Optional[int] = None,
) -> KpiSettings:
    """Upsert the singleton row using the sentinel-aware payload.

    Fields set to ``None`` are left alone (the column still resolves
    via env → default). The ``openai_api_key`` field has special
    semantics — see ``KEEP_API_KEY``.
    """
    row = get_row(db)
    if row is None:
        row = KpiSettings()
        db.add(row)

    # Provider / model / base_url. None = leave alone; empty string = clear.
    if payload.llm_provider is not None:
        row.llm_provider = (payload.llm_provider or None)
    if payload.openai_model is not None:
        row.openai_model = (payload.openai_model or None)
    if payload.openai_base_url is not None:
        row.openai_base_url = (payload.openai_base_url or None)

    # API key — sentinel-aware. Anything except KEEP_API_KEY is a write.
    if payload.openai_api_key != KEEP_API_KEY:
        row.openai_api_key = (payload.openai_api_key or None)

    if payload.token_budget is not None:
        row.token_budget = payload.token_budget
    if payload.max_iterations is not None:
        row.max_iterations = payload.max_iterations
    if payload.max_tokens_per_call is not None:
        row.max_tokens_per_call = payload.max_tokens_per_call

    # Domain knowledge — None = leave alone; "" = clear; anything else = save.
    if payload.domain_knowledge is not None:
        row.domain_knowledge = (payload.domain_knowledge.strip() or None)

    row.updated_by = updated_by
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Effective resolution — what the agent actually runs with
# ---------------------------------------------------------------------------

def get_effective(
    db: Session,
    *,
    env: Optional[dict] = None,
) -> EffectiveSettings:
    """Resolve the active config: DB → env → default per field.

    ``env`` lets tests inject a synthetic environment; in production
    callers pass ``os.environ``.
    """
    env = env if env is not None else os.environ
    row = get_row(db)

    # Provider name — DB takes precedence. Empty string in DB falls back
    # to env so an admin can "unset" via the UI.
    provider_name = _pick_str(
        row.llm_provider if row else None,
        env.get("KPI_LLM_PROVIDER"),
    )

    # Track whether DB supplied any of the key/model knobs — drives the
    # ``using_env_fallback`` flag the UI displays.
    using_env_fallback = True
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None

    if provider_name and provider_name.lower() in _OPENAI_DEFAULTS:
        cfg = _OPENAI_DEFAULTS[provider_name.lower()]

        # API key: prefer DB, else env.
        if row and row.openai_api_key:
            api_key = row.openai_api_key
            using_env_fallback = False
        else:
            api_key = (env.get(cfg["key_env"]) or "").strip() or None

        # Model: DB > env > default.
        model = _pick_str(
            row.openai_model if row else None,
            env.get(cfg["model_env"]),
            cfg["model"],
        )
        if row and row.openai_model:
            using_env_fallback = False

        # Base URL: DB > env > default.
        base_url = _pick_str(
            row.openai_base_url if row else None,
            env.get(cfg["base_url_env"]),
            cfg["base_url"],
        )

    # Caps — DB → env → constant.
    token_budget = _pick_int(
        row.token_budget if row else None,
        env.get("KPI_NL_TOKEN_BUDGET"),
        DEFAULT_TOKEN_BUDGET,
    )
    max_iterations = _pick_int(
        row.max_iterations if row else None,
        env.get("KPI_NL_MAX_ITERATIONS"),
        DEFAULT_MAX_ITERATIONS,
    )
    max_tokens_per_call = _pick_int(
        row.max_tokens_per_call if row else None,
        env.get("KPI_NL_MAX_TOKENS_PER_CALL"),
        DEFAULT_MAX_TOKENS_PER_CALL,
    )

    provider: Optional[LlmProvider] = None
    if provider_name and api_key and model and base_url:
        provider = OpenAICompatibleProvider(
            api_key=api_key,
            model=model,
            base_url=base_url,
            name=provider_name.lower(),
        )

    domain_knowledge = (row.domain_knowledge or "").strip() if row else ""

    # Pre-flight knobs. Resolution order: DB row → env var → True.
    # The env-var fallback exists so tests + ops can disable the loop
    # without writing to the DB; explicit DB value (including 0/False)
    # still takes precedence so admins can override env from the
    # Settings UI.
    if row and row.preflight_enabled is not None:
        pf_enabled = bool(row.preflight_enabled)
    else:
        env_pf = (env.get("KPI_PREFLIGHT_ENABLED") or "").strip().lower()
        if env_pf in ("0", "false", "no", "off"):
            pf_enabled = False
        else:
            pf_enabled = True
    pf_rounds = (
        int(row.preflight_max_rounds) if (row and row.preflight_max_rounds) else 5
    )
    pf_escalations = (
        int(row.preflight_user_escalations) if (row and row.preflight_user_escalations) else 2
    )
    # Clamp to the user-stated 5..10 range so a stray DB value can't
    # drive the loop into pathological territory.
    pf_rounds = max(1, min(10, pf_rounds))
    pf_escalations = max(0, min(5, pf_escalations))

    # Chat history threading — env-only for now (no DB column). Clamp
    # to 0..10 so a typo in the env can't blow the prompt up.
    chat_history_turns = _pick_int(
        None, env.get("KPI_CHAT_HISTORY_TURNS"), 3,
    )
    chat_history_turns = max(0, min(10, chat_history_turns))

    return EffectiveSettings(
        provider=provider,
        provider_name=(provider_name or None),
        model=model,
        has_key=bool(api_key),
        using_env_fallback=using_env_fallback,
        token_budget=token_budget,
        max_iterations=max_iterations,
        max_tokens_per_call=max_tokens_per_call,
        domain_knowledge=(domain_knowledge or None),
        preflight_enabled=pf_enabled,
        preflight_max_rounds=pf_rounds,
        preflight_user_escalations=pf_escalations,
        chat_history_turns=chat_history_turns,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_str(*candidates: Optional[str]) -> Optional[str]:
    """First non-empty candidate, trimmed. ``None`` when all empty."""
    for c in candidates:
        if c is None:
            continue
        s = str(c).strip()
        if s:
            return s
    return None


def _pick_int(*candidates) -> int:
    """First positive int candidate. The last candidate is the
    compile-time default and is always returned as a fallback."""
    for c in candidates[:-1]:
        if c is None or c == "":
            continue
        try:
            v = int(c)
            if v > 0:
                return v
        except (ValueError, TypeError):
            continue
    # Final candidate is the typed default — return as-is.
    return int(candidates[-1])
