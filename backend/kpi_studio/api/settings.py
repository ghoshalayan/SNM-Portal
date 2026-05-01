"""Runtime settings management — SuperAdmin only.

Endpoints:
  GET  /settings           current state + effective resolution
  PUT  /settings           write singleton row
  POST /settings/test      one-off test of the active provider

The API key is **write-only**: GET never returns it (only a flag).
PUT uses a sentinel ``KEEP_API_KEY`` for "no change" so the UI can
preserve the existing value when the user hasn't touched the field.

Gated to ``kpi:settings`` permission, which the host wires to
SuperAdmin in ``app/main.py``.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.providers.llm.base import LlmMessage, LlmProviderError
from kpi_studio.schemas import (
    SettingsResponse, SettingsTestRequest, SettingsTestResponse, SettingsUpdate,
)
from kpi_studio.services import settings_service


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _to_response(row, eff: settings_service.EffectiveSettings) -> SettingsResponse:
    """Build the GET response, merging the stored row + effective resolution.

    The API key never appears in the response — only a boolean. UI uses
    that boolean to show "set" vs "not set".
    """
    return SettingsResponse(
        llm_provider=(row.llm_provider if row else None),
        has_api_key=bool(row and row.openai_api_key),
        openai_model=(row.openai_model if row else None),
        openai_base_url=(row.openai_base_url if row else None),
        token_budget=(row.token_budget if row else None),
        max_iterations=(row.max_iterations if row else None),
        max_tokens_per_call=(row.max_tokens_per_call if row else None),
        domain_knowledge=(row.domain_knowledge if row else None),
        effective_provider=eff.provider_name,
        effective_model=eff.model,
        effective_token_budget=eff.token_budget,
        effective_max_iterations=eff.max_iterations,
        effective_max_tokens_per_call=eff.max_tokens_per_call,
        effective_has_key=eff.has_key,
        using_env_fallback=eff.using_env_fallback,
    )


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "",
        response_model=SettingsResponse,
        # ``kpi:settings`` is a SuperAdmin-only code in the host's
        # permission_checker (see app/main.py); ``kpi:view`` would be too
        # permissive given the page reveals provider + model details.
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def get_settings(
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ) -> SettingsResponse:
        row = settings_service.get_row(db)
        eff = settings_service.get_effective(db, env=os.environ)
        return _to_response(row, eff)

    @router.put(
        "",
        response_model=SettingsResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def update_settings(
        payload: SettingsUpdate,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> SettingsResponse:
        row = settings_service.update_row(
            db, payload, updated_by=_user_id(user),
        )
        eff = settings_service.get_effective(db, env=os.environ)
        return _to_response(row, eff)

    @router.post(
        "/test",
        response_model=SettingsTestResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def test_provider(
        _payload: SettingsTestRequest = SettingsTestRequest(),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ) -> SettingsTestResponse:
        """Round-trip the configured provider with a tiny prompt so the
        admin can verify the API key + model work without hunting in
        uvicorn logs. Cheap (returns 1-token response) and uses the
        same resolution path the agent uses."""
        eff = settings_service.get_effective(db, env=os.environ)
        if eff.provider is None:
            return SettingsTestResponse(
                ok=False,
                message="No provider configured. Set provider + API key + model first.",
                provider=eff.provider_name,
                model=eff.model,
            )
        try:
            r = eff.provider.complete(
                [LlmMessage(role="user", content="Reply with exactly the word 'pong'.")],
                max_tokens=8,
                temperature=0,
            )
            return SettingsTestResponse(
                ok=True,
                message=f"Provider responded: {r.text[:40]!r}",
                provider=eff.provider_name,
                model=r.model,
                latency_ms=r.latency_ms,
            )
        except LlmProviderError as exc:
            return SettingsTestResponse(
                ok=False,
                message=str(exc),
                provider=eff.provider_name,
                model=eff.model,
            )

    return router
