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
    # T-901 — OpenRouter. One key, many models behind ``model`` strings
    # like ``anthropic/claude-3.5-sonnet`` / ``openai/gpt-4o``.
    "openrouter": {
        "model": "anthropic/claude-3.5-sonnet",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "KPI_OPENROUTER_API_KEY",
        "model_env": "KPI_OPENROUTER_MODEL",
        "base_url_env": "KPI_OPENROUTER_BASE_URL",
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
    # 2026-05-25 — cost kill-switch for automatic healthcheck probes.
    # Default True for back-compat; admins flip off via the Health tab
    # when LLM-probe billing is a concern.
    healthcheck_auto_enabled: bool = True
    # 2026-05-25 — LLM call-log toggle + retention window.
    call_logging_enabled: bool = True
    call_log_retention_days: int = 7
    # Phase B2 — how many of the most recent (user, assistant) message
    # pairs to feed back into the agent on each chat turn so it can
    # follow up "now group that by region" / "and only for last
    # quarter". 0 disables threading entirely. Resolved env-only for
    # now; KpiSettings DB column can be added later if admins want a
    # UI toggle.
    chat_history_turns: int = 3
    # T-901: OpenRouter extras. Only sent as HTTP headers when the
    # provider is "openrouter"; ignored otherwise.
    openrouter_referer: Optional[str] = None
    openrouter_app_name: Optional[str] = None
    # T-902: Per-stage model routing. ``stage_models`` is the raw map
    # from KpiSettings (or None); ``default_stage_model`` is the
    # fallback when a stage isn't in the map. ``provider_for_stage()``
    # is the convenience builder that combines them with the resolved
    # provider/key/base_url.
    stage_models: Optional[dict[str, str]] = None
    default_stage_model: Optional[str] = None


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

    # T-901: OpenRouter extras.
    if payload.openrouter_referer is not None:
        row.openrouter_referer = (payload.openrouter_referer.strip() or None)
    if payload.openrouter_app_name is not None:
        row.openrouter_app_name = (payload.openrouter_app_name.strip() or None)

    # 2026-05-25 — automatic-healthcheck kill switch.
    if payload.healthcheck_auto_enabled is not None:
        row.healthcheck_auto_enabled = bool(payload.healthcheck_auto_enabled)

    # 2026-05-25 — LLM call-log kill switch + retention.
    if payload.call_logging_enabled is not None:
        row.call_logging_enabled = bool(payload.call_logging_enabled)
    if payload.call_log_retention_days is not None:
        row.call_log_retention_days = max(1, min(365, int(payload.call_log_retention_days)))

    # T-902 + multi-provider refactor: stage routing supports two
    # entry shapes:
    #   * legacy string:   "anthropic/claude-3.5-sonnet"
    #   * new object:      {"provider_config_id": 3, "model": "..."}
    # Empty / blank entries (in either shape) get dropped — they mean
    # "no override; fall through to default_stage_model → eff.model".
    if payload.stage_models is not None:
        cleaned: dict = {}
        for k, v in payload.stage_models.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, str):
                vs = v.strip()
                if vs:
                    cleaned[k] = vs
            elif isinstance(v, dict):
                cid = v.get("provider_config_id")
                model = (v.get("model") or "").strip() if v.get("model") else ""
                # Keep the row when EITHER side is set so the resolver
                # can fall through cleanly. An entry with neither is
                # equivalent to absence; drop it.
                if isinstance(cid, int) or model:
                    entry: dict = {}
                    if isinstance(cid, int):
                        entry["provider_config_id"] = cid
                    if model:
                        entry["model"] = model
                    cleaned[k] = entry
        row.stage_models = cleaned if cleaned else None
    if payload.default_stage_model is not None:
        row.default_stage_model = (payload.default_stage_model.strip() or None)

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

    # T-901: OpenRouter extras. DB-only — env equivalent isn't worth a
    # new var when the admin can just paste into the UI.
    openrouter_referer = (row.openrouter_referer or "").strip() if row else ""
    openrouter_app_name = (row.openrouter_app_name or "").strip() if row else ""

    provider: Optional[LlmProvider] = None
    if provider_name and api_key and model and base_url:
        provider = _build_provider(
            name=provider_name.lower(),
            api_key=api_key, model=model, base_url=base_url,
            openrouter_referer=openrouter_referer or None,
            openrouter_app_name=openrouter_app_name or None,
        )

    # T-902: per-stage routing map + default fallback.
    stage_models: Optional[dict[str, str]] = None
    if row and row.stage_models:
        stage_models = {
            k: v for k, v in row.stage_models.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        } or None
    default_stage_model = (row.default_stage_model or "").strip() if row else ""

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

    # Healthcheck-auto kill switch (2026-05-25). Same resolution as
    # preflight: explicit DB value wins; otherwise read env; default
    # True for back-compat with deployments that haven't seen the
    # column yet.
    if row and row.healthcheck_auto_enabled is not None:
        hc_auto = bool(row.healthcheck_auto_enabled)
    else:
        env_hc = (env.get("KPI_HEALTHCHECK_AUTO_ENABLED") or "").strip().lower()
        hc_auto = env_hc not in ("0", "false", "no", "off")

    # Call-logging kill switch — same DB > env > default(True) pattern.
    if row and row.call_logging_enabled is not None:
        call_log_on = bool(row.call_logging_enabled)
    else:
        env_cl = (env.get("KPI_CALL_LOGGING_ENABLED") or "").strip().lower()
        call_log_on = env_cl not in ("0", "false", "no", "off")
    call_log_days = _pick_int(
        row.call_log_retention_days if row else None,
        env.get("KPI_CALL_LOG_RETENTION_DAYS"),
        7,
    )
    call_log_days = max(1, min(365, call_log_days))

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
        healthcheck_auto_enabled=hc_auto,
        call_logging_enabled=call_log_on,
        call_log_retention_days=call_log_days,
        openrouter_referer=(openrouter_referer or None),
        openrouter_app_name=(openrouter_app_name or None),
        stage_models=stage_models,
        default_stage_model=(default_stage_model or None),
    )


# ---------------------------------------------------------------------------
# T-902 — Per-stage provider builder
# ---------------------------------------------------------------------------
# Multi-provider semantics (2026-05-25 refactor):
#
# ``stage_models`` JSON entries can now be EITHER:
#   * a string (legacy): ``"openai/gpt-4o-mini"`` — uses the single
#     provider configured on KpiSettings.
#   * an object (new):   ``{"provider_config_id": 3, "model": "openai/gpt-4o-mini"}``
#     — instantiates the named provider config.
#
# ``resolve_stage_model`` returns the model string for either shape;
# ``resolve_stage_provider_config_id`` returns the config id (or None
# when the entry is legacy / unset).
#
# ``provider_for_stage`` consults provider_config_service when the
# new shape is present and falls back to the legacy single-provider
# path when it isn't.


def _stage_entry(eff: EffectiveSettings, stage_key: str):
    """Pull the raw stage entry (str / dict / None) from the routing map."""
    if not eff.stage_models or not isinstance(eff.stage_models, dict):
        return None
    return eff.stage_models.get(stage_key)


def resolve_stage_provider_config_id(
    eff: EffectiveSettings, stage_key: str,
) -> Optional[int]:
    """Return the config id assigned to this stage, or None for legacy /
    unset entries (which use the single-provider fallback)."""
    entry = _stage_entry(eff, stage_key)
    if isinstance(entry, dict):
        cid = entry.get("provider_config_id")
        if isinstance(cid, int):
            return cid
    return None


def resolve_stage_model(
    eff: EffectiveSettings, stage_key: str, *,
    db: Optional[Session] = None,
) -> Optional[str]:
    """The model string that would be used for ``stage_key``.

    Resolution order (first hit wins):

    1. The stage entry's explicit ``model`` (per-stage override).
    2. **2026-05-26**: when the stage entry picks a provider but leaves
       model blank, use that provider config's ``default_model``. This
       is what an admin expects when they pick "OpenRouter" for a
       stage and leave Model blank — the provider already declared
       which model it prefers; the global fallback shouldn't override
       it. Requires ``db``; silently skipped when None.
    3. The global ``default_stage_model`` (used when a stage has no
       routing entry at all, or a legacy string entry that's blank).
    4. The ``is_default=True`` provider config's ``default_model`` —
       the system-wide fallback when nothing else is set. Requires
       ``db``.
    5. ``eff.model`` — legacy single-provider model.
    """
    entry = _stage_entry(eff, stage_key)
    if isinstance(entry, dict):
        m = (entry.get("model") or "").strip()
        if m:
            return m
        cid = entry.get("provider_config_id")
        if isinstance(cid, int) and db is not None:
            from kpi_studio.services import provider_config_service
            row = provider_config_service.get(db, cid)
            if row is not None and (row.default_model or "").strip():
                return row.default_model.strip()
    elif isinstance(entry, str):
        m = entry.strip()
        if m:
            return m
    if eff.default_stage_model:
        return eff.default_stage_model
    if db is not None:
        from kpi_studio.services import provider_config_service
        default_row = provider_config_service.get_default(db)
        if default_row is not None and (default_row.default_model or "").strip():
            return default_row.default_model.strip()
    return eff.model


def provider_for_stage(
    eff: EffectiveSettings,
    stage_key: str,
    *,
    db: Optional[Session] = None,
) -> Optional[LlmProvider]:
    """Return an LlmProvider configured for a specific pipeline stage.

    Resolution paths (first hit wins):

    1. Stage has a ``provider_config_id`` → look it up via
       ``provider_config_service``, build with the stage's model.
       Requires ``db``; falls back if not supplied.
    2. **2026-05-25**: stage has no per-stage provider → use the
       system-default provider config (``is_default=True``) when one
       exists. Model resolves to stage entry > ``default_stage_model``
       > the default provider's ``default_model``.
    3. Stage is in the legacy string format / unrouted → use the
       legacy single-provider (``eff.provider``) with the stage's
       model swapped in.

    Returns None when nothing usable is configured.
    """
    chosen_model = resolve_stage_model(eff, stage_key, db=db) or eff.model
    cid = resolve_stage_provider_config_id(eff, stage_key)

    # ---- Path 1: explicit provider config ------------------------------
    if cid is not None and db is not None:
        from kpi_studio.services import provider_config_service
        row = provider_config_service.get(db, cid)
        if row is not None and row.is_active:
            try:
                return provider_config_service.build_provider(
                    row, model=chosen_model,
                )
            except ValueError:
                # Bad config (missing base_url / model) — fall through
                # so the caller at least gets the legacy provider rather
                # than a hard None.
                pass

    # ---- Path 2: system-default provider (2026-05-25) ------------------
    # When a stage has no per-stage cid AND we have a DB session, prefer
    # the explicit "is_default=True" row over the legacy single-provider
    # path. This is what makes the new "Set as default" affordance the
    # canonical fallback target without the admin having to repeat it
    # on every stage row.
    if db is not None:
        from kpi_studio.services import provider_config_service
        default_row = provider_config_service.get_default(db)
        if default_row is not None and default_row.is_active:
            # If the stage didn't supply a model AND no global
            # default_stage_model is set, fall back to the default
            # provider's own default_model — that's the whole point of
            # storing it on the row.
            model_for_call = chosen_model or (default_row.default_model or "").strip()
            try:
                return provider_config_service.build_provider(
                    default_row, model=model_for_call,
                )
            except ValueError:
                pass

    # ---- Path 3: legacy single-provider fallback -----------------------
    if eff.provider is None or not eff.has_key or not eff.provider_name:
        return None
    if not chosen_model:
        return eff.provider  # nothing to swap, return the existing one as-is

    default = eff.provider
    return _build_provider(
        name=eff.provider_name,
        api_key=_extract_api_key(default),
        model=chosen_model,
        base_url=_extract_base_url(default),
        openrouter_referer=eff.openrouter_referer,
        openrouter_app_name=eff.openrouter_app_name,
    )


def _build_provider(
    *,
    name: str,
    api_key: str,
    model: str,
    base_url: str,
    openrouter_referer: Optional[str],
    openrouter_app_name: Optional[str],
) -> LlmProvider:
    """Construct an OpenAICompatibleProvider with provider-specific
    extra headers. Centralised so the env-bootstrap path, the stage
    builder, and the healthcheck produce identical providers for the
    same inputs."""
    extras: dict[str, str] = {}
    if name == "openrouter":
        if openrouter_referer:
            extras["HTTP-Referer"] = openrouter_referer
        if openrouter_app_name:
            extras["X-Title"] = openrouter_app_name
    return OpenAICompatibleProvider(
        api_key=api_key, model=model, base_url=base_url, name=name,
        extra_headers=(extras or None),
    )


def _extract_api_key(provider: LlmProvider) -> str:
    """Pull the API key off an OpenAICompatibleProvider. Internal —
    only used by ``provider_for_stage`` to clone a provider with a
    different model. Wrapped so future provider types can override."""
    return getattr(provider, "_api_key", "")


def _extract_base_url(provider: LlmProvider) -> str:
    return getattr(provider, "_base_url", "")


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
