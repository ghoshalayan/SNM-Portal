"""CRUD + provider-instantiation for kpi_llm_provider_config.

One row = one configured LLM provider. Per-stage routing in
``KpiSettings.stage_models`` picks WHICH config_id to use per pipeline
stage, then this module builds the actual ``LlmProvider`` instance with
that config's key + base_url + extras.

The legacy single-provider columns on ``KpiSettings`` are still read by
``settings_service.get_effective`` as a fallback — when a stage's
``stage_models`` entry doesn't carry a ``provider_config_id``, the
agent uses the legacy single-provider path. This keeps unmigrated
stages working until they're re-saved through the new UI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from kpi_studio.models import KpiLlmProviderConfig, PROVIDER_KINDS
from kpi_studio.providers.llm.base import LlmProvider
from kpi_studio.providers.llm.openai_compatible import OpenAICompatibleProvider


log = logging.getLogger(__name__)


# Same defaults as the env-bootstrap factory uses. Per-kind hardcoded
# defaults for base_url + model — when a provider config leaves
# base_url blank, we substitute these.
KIND_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model_default": "gpt-5.4-nano",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model_default": "anthropic/claude-3.5-sonnet",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "model_default": "llama-3.3-70b",
    },
    "ollama_cloud": {
        "base_url": "https://ollama.com/v1",
        "model_default": "llama3.3",
    },
    "azure_openai": {
        # No public default — admin must paste the resource URL.
        "base_url": "",
        "model_default": "gpt-4o",
    },
}


@dataclass(frozen=True)
class ProviderConfigSummary:
    """Wire-safe summary — never carries the raw API key."""
    provider_config_id: int
    kind: str
    display_name: str
    base_url: Optional[str]
    has_api_key: bool
    is_active: bool
    description: Optional[str]
    openrouter_referer: Optional[str]
    openrouter_app_name: Optional[str]
    # Admin-entered default model for this provider. Falls back to the
    # kind's KIND_DEFAULTS entry when the row's column is blank
    # (legacy rows pre-2026-05-25 that haven't been edited yet).
    default_model: str
    is_default: bool


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_active(db: Session) -> list[KpiLlmProviderConfig]:
    return (
        db.query(KpiLlmProviderConfig)
        .filter(KpiLlmProviderConfig.is_active == True)  # noqa: E712
        .order_by(KpiLlmProviderConfig.display_name.asc())
        .all()
    )


def list_all(db: Session) -> list[KpiLlmProviderConfig]:
    return (
        db.query(KpiLlmProviderConfig)
        .order_by(KpiLlmProviderConfig.is_active.desc(),
                  KpiLlmProviderConfig.display_name.asc())
        .all()
    )


def get(db: Session, provider_config_id: int) -> Optional[KpiLlmProviderConfig]:
    return db.get(KpiLlmProviderConfig, provider_config_id)


def create(
    db: Session,
    *,
    kind: str,
    display_name: str,
    api_key: str,
    default_model: str,
    base_url: Optional[str] = None,
    openrouter_referer: Optional[str] = None,
    openrouter_app_name: Optional[str] = None,
    description: Optional[str] = None,
    is_default: bool = False,
    created_by: Optional[int] = None,
) -> KpiLlmProviderConfig:
    kind = (kind or "").strip().lower()
    if kind not in PROVIDER_KINDS:
        raise ValueError(f"Unknown provider kind: {kind!r}")
    if not (display_name or "").strip():
        raise ValueError("display_name is required")
    if not (api_key or "").strip():
        raise ValueError("api_key is required")
    if not (default_model or "").strip():
        raise ValueError(
            "default_model is required (the per-provider default model "
            "string used by stage routing when a stage leaves the Model "
            "field blank).",
        )
    row = KpiLlmProviderConfig(
        kind=kind,
        display_name=display_name.strip(),
        api_key=api_key.strip(),
        default_model=default_model.strip(),
        base_url=(base_url or "").strip() or None,
        openrouter_referer=(openrouter_referer or "").strip() or None,
        openrouter_app_name=(openrouter_app_name or "").strip() or None,
        description=(description or "").strip() or None,
        is_active=True,
        is_default=False,  # set via _enforce_single_default below
        created_by=created_by,
        updated_by=created_by,
    )
    db.add(row)
    db.flush()  # need provider_config_id for the invariant helper
    # If the caller asked for default OR no other default exists,
    # promote this row. Bootstrap case (first ever provider) auto-
    # promotes so the resolver always has a fallback.
    if is_default or not _any_default_exists(db, exclude_id=row.provider_config_id):
        _enforce_single_default(db, row.provider_config_id)
    db.commit()
    db.refresh(row)
    return row


def update(
    db: Session,
    provider_config_id: int,
    *,
    kind: Optional[str] = None,
    display_name: Optional[str] = None,
    api_key: Optional[str] = None,
    default_model: Optional[str] = None,
    base_url: Optional[str] = None,
    openrouter_referer: Optional[str] = None,
    openrouter_app_name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_default: Optional[bool] = None,
    updated_by: Optional[int] = None,
) -> KpiLlmProviderConfig:
    row = get(db, provider_config_id)
    if row is None:
        raise LookupError(f"Provider config {provider_config_id} not found")

    if kind is not None:
        k = kind.strip().lower()
        if k not in PROVIDER_KINDS:
            raise ValueError(f"Unknown provider kind: {kind!r}")
        row.kind = k
    if display_name is not None:
        if not display_name.strip():
            raise ValueError("display_name cannot be empty")
        row.display_name = display_name.strip()
    if api_key is not None:
        # Empty string explicitly clears? No — an empty key would
        # break the provider; treat empty as "leave alone" too. The
        # caller's sentinel handling lives at the API edge.
        if api_key.strip():
            row.api_key = api_key.strip()
    if default_model is not None:
        if not default_model.strip():
            raise ValueError("default_model cannot be empty")
        row.default_model = default_model.strip()
    if base_url is not None:
        row.base_url = base_url.strip() or None
    if openrouter_referer is not None:
        row.openrouter_referer = openrouter_referer.strip() or None
    if openrouter_app_name is not None:
        row.openrouter_app_name = openrouter_app_name.strip() or None
    if description is not None:
        row.description = description.strip() or None
    if is_active is not None:
        row.is_active = is_active
        # Soft-deleting the current default would leave nothing as
        # the fallback; promote the next active row before clearing.
        if not is_active and row.is_default:
            _demote_and_promote_next(db, demoted_id=row.provider_config_id)
    if is_default is True:
        _enforce_single_default(db, row.provider_config_id)
    elif is_default is False and row.is_default:
        # Explicit "no longer default" — promote the next active row
        # so something remains the fallback.
        _demote_and_promote_next(db, demoted_id=row.provider_config_id)
    row.updated_by = updated_by

    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# is_default invariant helpers
# ---------------------------------------------------------------------------
# Exactly one provider config is the system default at any time. The
# UI exposes the toggle as "Set as default" on the provider dialog;
# the service guarantees the invariant so consumers (resolver,
# healthcheck) can rely on "first row where is_default=True".


def _any_default_exists(db: Session, *, exclude_id: Optional[int] = None) -> bool:
    q = db.query(KpiLlmProviderConfig).filter(KpiLlmProviderConfig.is_default == True)  # noqa: E712
    if exclude_id is not None:
        q = q.filter(KpiLlmProviderConfig.provider_config_id != exclude_id)
    return db.query(q.exists()).scalar() is True


def _enforce_single_default(db: Session, new_default_id: int) -> None:
    """Set ``new_default_id`` as the sole default in one transaction.
    Caller is responsible for the surrounding commit."""
    db.query(KpiLlmProviderConfig).filter(
        KpiLlmProviderConfig.provider_config_id != new_default_id,
        KpiLlmProviderConfig.is_default == True,  # noqa: E712
    ).update({"is_default": False}, synchronize_session=False)
    db.query(KpiLlmProviderConfig).filter(
        KpiLlmProviderConfig.provider_config_id == new_default_id,
    ).update({"is_default": True}, synchronize_session=False)


def _demote_and_promote_next(db: Session, *, demoted_id: int) -> None:
    """The previous default is being cleared (soft-delete or explicit
    'unset default'). Promote the next active provider so something
    remains the fallback. No-op when no other active row exists."""
    db.query(KpiLlmProviderConfig).filter(
        KpiLlmProviderConfig.provider_config_id == demoted_id,
    ).update({"is_default": False}, synchronize_session=False)
    candidate = (
        db.query(KpiLlmProviderConfig)
        .filter(KpiLlmProviderConfig.is_active == True,  # noqa: E712
                KpiLlmProviderConfig.provider_config_id != demoted_id)
        .order_by(KpiLlmProviderConfig.provider_config_id.asc())
        .first()
    )
    if candidate is not None:
        candidate.is_default = True


def get_default(db: Session) -> Optional[KpiLlmProviderConfig]:
    """The provider config marked as system default (or None when no
    row has the flag)."""
    return (
        db.query(KpiLlmProviderConfig)
        .filter(KpiLlmProviderConfig.is_default == True)  # noqa: E712
        .first()
    )


def delete(db: Session, provider_config_id: int) -> None:
    """Hard delete. The UI calls this when an admin wants to retire a
    provider config entirely; soft-delete via ``is_active=False`` is
    available through ``update`` for less destructive removal.

    Caveat: any ``stage_models`` entry still pointing at this id will
    fall through to the legacy resolver on next request. The API guards
    against deleting a config that's still referenced (returns 409).
    """
    row = get(db, provider_config_id)
    if row is None:
        return
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Summary / projection
# ---------------------------------------------------------------------------

def to_summary(row: KpiLlmProviderConfig) -> ProviderConfigSummary:
    cfg = KIND_DEFAULTS.get(row.kind, {})
    # Row column wins; KIND_DEFAULTS is the back-compat fallback for
    # legacy rows that pre-date the default_model column.
    resolved_default = (row.default_model or "").strip() or cfg.get("model_default", "")
    return ProviderConfigSummary(
        provider_config_id=row.provider_config_id,
        kind=row.kind,
        display_name=row.display_name,
        base_url=row.base_url or cfg.get("base_url") or None,
        has_api_key=bool(row.api_key),
        is_active=row.is_active,
        description=row.description,
        openrouter_referer=row.openrouter_referer,
        openrouter_app_name=row.openrouter_app_name,
        default_model=resolved_default,
        is_default=bool(row.is_default),
    )


# ---------------------------------------------------------------------------
# Provider instantiation
# ---------------------------------------------------------------------------

def build_provider(
    row: KpiLlmProviderConfig,
    *,
    model: Optional[str] = None,
) -> LlmProvider:
    """Construct an LlmProvider for this config.

    ``model`` is per-call: stage routing passes the stage's chosen
    model string. When None, falls back to KIND_DEFAULTS for the
    config's kind (useful for the "test connection" affordance where
    the admin just wants to confirm the key + URL work without picking
    a model first).
    """
    cfg = KIND_DEFAULTS.get(row.kind, {})
    # Resolution order for the model: per-call override > row's
    # admin-entered default > KIND_DEFAULTS legacy fallback.
    chosen_model = (
        (model or "").strip()
        or (row.default_model or "").strip()
        or cfg.get("model_default")
        or ""
    )
    if not chosen_model:
        raise ValueError(
            f"No model available for provider config {row.provider_config_id} "
            f"(kind={row.kind!r}); pass model explicitly."
        )
    base_url = (row.base_url or "").strip() or cfg.get("base_url") or ""
    if not base_url:
        raise ValueError(
            f"No base_url for provider config {row.provider_config_id} "
            f"(kind={row.kind!r}); set it explicitly."
        )

    extras: dict[str, str] = {}
    if row.kind == "openrouter":
        if row.openrouter_referer:
            extras["HTTP-Referer"] = row.openrouter_referer
        if row.openrouter_app_name:
            extras["X-Title"] = row.openrouter_app_name

    return OpenAICompatibleProvider(
        api_key=row.api_key,
        model=chosen_model,
        base_url=base_url,
        name=row.kind,
        extra_headers=(extras or None),
        provider_config_id=row.provider_config_id,
        provider_label=row.display_name,
    )


def default_model_for_kind(kind: str) -> str:
    """Used by the UI to pre-fill the model field when an admin picks
    a kind on a new config, AND by the legacy code paths that haven't
    been migrated to read ``row.default_model`` yet. New code should
    prefer ``row.default_model`` since the admin may have edited it."""
    return KIND_DEFAULTS.get(kind or "", {}).get("model_default", "")


def base_url_for_kind(kind: str) -> str:
    return KIND_DEFAULTS.get(kind or "", {}).get("base_url", "")
