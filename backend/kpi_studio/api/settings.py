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
    HealthcheckProbe, HealthcheckRequest, HealthcheckResponse,
    SettingsResponse, SettingsTestRequest, SettingsTestResponse, SettingsUpdate,
    StageDefinition,
)
from kpi_studio.services import provider_healthcheck, settings_service
from kpi_studio.stages import STAGES, all_stage_keys


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _to_response(
    row, eff: settings_service.EffectiveSettings, *,
    db: Optional[Session] = None,
) -> SettingsResponse:
    """Build the GET response, merging the stored row + effective resolution.

    The API key never appears in the response — only a boolean. UI uses
    that boolean to show "set" vs "not set".

    ``db`` is required so the per-stage model resolver can consult
    each stage-provider's ``default_model`` (per 2026-05-26 resolver
    fix). When None, the resolver still works but skips that step,
    falling back to the legacy global-default behaviour.
    """
    # T-902: compute the effective per-stage model map so the UI can
    # render "what would run today" alongside what the admin has
    # explicitly configured.
    effective_stage_models = {
        key: model
        for key in all_stage_keys()
        if (model := settings_service.resolve_stage_model(eff, key, db=db))
    }
    return SettingsResponse(
        healthcheck_auto_enabled=eff.healthcheck_auto_enabled,
        call_logging_enabled=eff.call_logging_enabled,
        call_log_retention_days=eff.call_log_retention_days,
        llm_provider=(row.llm_provider if row else None),
        has_api_key=bool(row and row.openai_api_key),
        openai_model=(row.openai_model if row else None),
        openai_base_url=(row.openai_base_url if row else None),
        token_budget=(row.token_budget if row else None),
        max_iterations=(row.max_iterations if row else None),
        max_tokens_per_call=(row.max_tokens_per_call if row else None),
        domain_knowledge=(row.domain_knowledge if row else None),
        openrouter_referer=(row.openrouter_referer if row else None),
        openrouter_app_name=(row.openrouter_app_name if row else None),
        stage_models=(dict(row.stage_models) if row and row.stage_models else None),
        default_stage_model=(row.default_stage_model if row else None),
        stages=[
            StageDefinition(
                key=s.key, label=s.label,
                description=s.description, built=s.built,
            )
            for s in STAGES
        ],
        effective_stage_models=effective_stage_models,
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
        return _to_response(row, eff, db=db)

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
        # T-004: write the row first, then probe the new config.
        # Refuse the change (via 400) if probe fails AND the admin
        # didn't pass force=true. We have to write before probing
        # because the resolver reads from the DB; on failure with
        # force=false we roll back so the bad config doesn't leak.
        from fastapi import HTTPException
        prior_row = settings_service.get_row(db)
        prior_snapshot = (
            (prior_row.llm_provider, prior_row.openai_api_key,
             prior_row.openai_model, prior_row.openai_base_url,
             dict(prior_row.stage_models) if prior_row.stage_models else None,
             prior_row.default_stage_model)
            if prior_row is not None else None
        )

        row = settings_service.update_row(
            db, payload, updated_by=_user_id(user),
        )
        # New config means cached healthcheck is stale.
        provider_healthcheck.invalidate_cache()

        # 2026-05-25 — admin can disable the automatic healthcheck
        # entirely (cost concern: each probe is a billable LLM call,
        # and the rollback-on-failure path was preventing saves when
        # legacy model strings fell through to OpenRouter).
        # When off: commit immediately, no probes.
        eff_after_save = settings_service.get_effective(db, env=os.environ)
        if not eff_after_save.healthcheck_auto_enabled:
            return _to_response(row, eff_after_save, db=db)

        # Probe. ``force=True`` here means "don't read the cache"
        # (which we just invalidated anyway) — NOT the admin's force flag.
        result = provider_healthcheck.run_healthcheck(db, force=True)
        if not result.overall_ok and not payload.force:
            # Roll back the changed columns. The audit (updated_by) and
            # any rev-tracking the host might add will be lost — that's
            # the price of refusing the save.
            if prior_snapshot is not None:
                (row.llm_provider, row.openai_api_key, row.openai_model,
                 row.openai_base_url, row.stage_models,
                 row.default_stage_model) = prior_snapshot
                db.commit()
            else:
                # No prior row existed — drop the one we just created.
                db.delete(row)
                db.commit()
            failures = [
                f"{p.provider}/{p.model}: {p.error or 'unknown'}"
                for p in result.probes if not p.ok
            ]
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "healthcheck_failed",
                    "message": (
                        "Provider healthcheck failed on the new "
                        "configuration. Save rejected. Set ``force=true`` "
                        "in the PUT body to save anyway."
                    ),
                    "failures": failures,
                },
            )

        eff = settings_service.get_effective(db, env=os.environ)
        return _to_response(row, eff, db=db)

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

    @router.post(
        "/healthcheck",
        response_model=HealthcheckResponse,
        dependencies=[Depends(perm("kpi:settings"))],
    )
    def healthcheck(
        payload: HealthcheckRequest = HealthcheckRequest(),
        db: Session = Depends(db_dep),
        _user: Any = Depends(auth),
    ) -> HealthcheckResponse:
        """T-004 — probe every configured stage. ``force=true`` bypasses
        the in-process cache so the admin sees fresh probe results
        instead of a 5-minute-old cached state."""
        result = provider_healthcheck.run_healthcheck(
            db, force=payload.force, trigger_source="healthcheck_manual",
        )
        return HealthcheckResponse(
            overall_ok=result.overall_ok,
            cached=result.cached,
            checked_at=result.checked_at.isoformat(),
            probes=[
                HealthcheckProbe(
                    provider=p.provider, model=p.model, ok=p.ok,
                    latency_ms=p.latency_ms, error=p.error,
                    stages=p.stages,
                )
                for p in result.probes
            ],
        )

    return router
