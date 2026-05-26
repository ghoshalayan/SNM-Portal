"""Multi-provider config API (refactor of T-901+T-902, shipped 2026-05-25).

CRUD over ``kpi_llm_provider_config`` + a per-provider Test endpoint
that does a real round-trip and echoes enough detail to diagnose
"is this hitting the right service" without leaking the API key.

All endpoints SuperAdmin-only (gated to ``kpi:settings``).

Routes (mounted at ``/api/v1/kpi/settings/providers``):

  GET    /                       list every configured provider (active + inactive)
  POST   /                       create a new provider config
  GET    /{id}                   one provider config
  PUT    /{id}                   update (KEEP sentinel for api_key)
  DELETE /{id}                   hard-delete (use is_active=false for soft)
  POST   /{id}/test              probe the provider with a 1-token completion
"""
from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.providers.llm.base import LlmMessage, LlmProviderError
from kpi_studio.schemas import (
    KEEP_API_KEY,
    ProviderConfigCreate,
    ProviderConfigListResponse,
    ProviderConfigPayload,
    ProviderConfigUpdate,
    ProviderTestRequest,
    ProviderTestResponse,
)
from kpi_studio.services import call_logger, provider_config_service, provider_healthcheck
from kpi_studio.models import PROVIDER_KINDS


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _to_payload(row) -> ProviderConfigPayload:
    summary = provider_config_service.to_summary(row)
    return ProviderConfigPayload(
        provider_config_id=summary.provider_config_id,
        kind=summary.kind,
        display_name=summary.display_name,
        base_url=summary.base_url,
        has_api_key=summary.has_api_key,
        is_active=summary.is_active,
        description=summary.description,
        openrouter_referer=summary.openrouter_referer,
        openrouter_app_name=summary.openrouter_app_name,
        default_model=summary.default_model,
        is_default=summary.is_default,
    )


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "",
        response_model=ProviderConfigListResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def list_providers(
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        rows = provider_config_service.list_all(db)
        return ProviderConfigListResponse(
            items=[_to_payload(r) for r in rows],
            total=len(rows),
            kinds=list(PROVIDER_KINDS),
        )

    @router.post(
        "",
        response_model=ProviderConfigPayload,
        status_code=status.HTTP_201_CREATED,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def create_provider(
        payload: ProviderConfigCreate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ):
        try:
            row = provider_config_service.create(
                db,
                kind=payload.kind,
                display_name=payload.display_name,
                api_key=payload.api_key,
                default_model=payload.default_model,
                base_url=payload.base_url,
                openrouter_referer=payload.openrouter_referer,
                openrouter_app_name=payload.openrouter_app_name,
                description=payload.description,
                is_default=payload.is_default,
                created_by=_user_id(user),
            )
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        # Invalidate healthcheck cache so the new provider gets probed
        # on the next page load.
        provider_healthcheck.invalidate_cache()
        return _to_payload(row)

    @router.get(
        "/{provider_config_id}",
        response_model=ProviderConfigPayload,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def get_provider(
        provider_config_id: int,
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        row = provider_config_service.get(db, provider_config_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")
        return _to_payload(row)

    @router.put(
        "/{provider_config_id}",
        response_model=ProviderConfigPayload,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def update_provider(
        provider_config_id: int,
        payload: ProviderConfigUpdate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ):
        # KEEP sentinel: pass None to the service when the caller didn't
        # touch the key. Any other string (including "") becomes a
        # write — but the service treats empty as "leave alone too"
        # (an empty key would brick the provider).
        api_key = None if payload.api_key == KEEP_API_KEY else payload.api_key
        try:
            row = provider_config_service.update(
                db, provider_config_id,
                kind=payload.kind,
                display_name=payload.display_name,
                api_key=api_key,
                default_model=payload.default_model,
                base_url=payload.base_url,
                openrouter_referer=payload.openrouter_referer,
                openrouter_app_name=payload.openrouter_app_name,
                description=payload.description,
                is_active=payload.is_active,
                is_default=payload.is_default,
                updated_by=_user_id(user),
            )
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        provider_healthcheck.invalidate_cache()
        return _to_payload(row)

    @router.delete(
        "/{provider_config_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def delete_provider(
        provider_config_id: int,
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        # Refuse delete when the provider is still referenced by a
        # stage_models entry — the admin should either soft-delete
        # (is_active=false) or re-route the stages first.
        from kpi_studio.services import settings_service
        from kpi_studio.stages import all_stage_keys
        eff = settings_service.get_effective(db, env=None)
        for k in all_stage_keys():
            cid = settings_service.resolve_stage_provider_config_id(eff, k)
            if cid == provider_config_id:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"Provider config {provider_config_id} is still routed by "
                    f"stage {k!r}. Re-route the stage to a different provider "
                    f"(or soft-delete via is_active=false) before deleting.",
                )
        provider_config_service.delete(db, provider_config_id)
        provider_healthcheck.invalidate_cache()
        return None

    @router.post(
        "/{provider_config_id}/test",
        response_model=ProviderTestResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def test_provider(
        provider_config_id: int,
        payload: ProviderTestRequest = ProviderTestRequest(),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ):
        """Real round-trip to the configured provider. Returns enough
        detail for the admin to diagnose 'is this hitting OpenAI or
        OpenRouter' without leaking the API key.

        Sends a 'reply with pong' prompt with up to 16 tokens; echoes
        the provider's reported model + first 80 chars of response."""
        row = provider_config_service.get(db, provider_config_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

        # Resolution order matches the agent's runtime resolver
        # (see provider_config_service.build_provider): per-call
        # override > row's admin-entered default > KIND_DEFAULTS legacy
        # fallback. The old code skipped the row's default_model and
        # went straight to KIND_DEFAULTS, so editing the Default model
        # on the card had no effect on Test connection.
        chosen_model = (
            (payload.model or "").strip()
            or (row.default_model or "").strip()
            or provider_config_service.default_model_for_kind(row.kind)
        )
        base_url = row.base_url or \
            provider_config_service.base_url_for_kind(row.kind)

        try:
            prov = provider_config_service.build_provider(row, model=chosen_model)
        except ValueError as exc:
            return ProviderTestResponse(
                provider_config_id=row.provider_config_id,
                display_name=row.display_name,
                kind=row.kind,
                base_url=base_url,
                model_used=chosen_model or "(unset)",
                ok=False,
                error=str(exc),
            )

        started = time.perf_counter()
        try:
            # Open call-log context so this single probe shows up in
            # the admin's Call log tab tagged as a provider_test (and
            # not lumped under chat / nl_generate noise).
            with call_logger.log_context(
                trigger_source="provider_test",
                user_id=_user_id(_user),
            ):
                r = prov.complete(
                    [LlmMessage(
                        role="user",
                        content="Reply with the single word 'pong' and nothing else.",
                    )],
                    max_tokens=16,
                    temperature=0.0,
                )
            latency = int((time.perf_counter() - started) * 1000)
            return ProviderTestResponse(
                provider_config_id=row.provider_config_id,
                display_name=row.display_name,
                kind=row.kind,
                base_url=base_url,
                model_used=chosen_model,
                ok=True,
                latency_ms=latency,
                response_model=r.model,
                response_preview=(r.text or "")[:80],
            )
        except LlmProviderError as exc:
            return ProviderTestResponse(
                provider_config_id=row.provider_config_id,
                display_name=row.display_name,
                kind=row.kind,
                base_url=base_url,
                model_used=chosen_model,
                ok=False,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderTestResponse(
                provider_config_id=row.provider_config_id,
                display_name=row.display_name,
                kind=row.kind,
                base_url=base_url,
                model_used=chosen_model,
                ok=False,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"{type(exc).__name__}: {exc!r}",
            )

    return router
