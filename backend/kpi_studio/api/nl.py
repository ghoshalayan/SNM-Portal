"""Natural-language → SQL endpoints.

Endpoints:
  GET  /nl/status     is the LLM provider configured?
  POST /nl/generate   prompt → SQL + explanation + validation
                      ``mode='agent'`` (default, Phase A7) runs the
                      tool-use loop; ``mode='single'`` (Phase A3 path)
                      one-shots the prompt with the full schema as context.

The user always reviews the generated SQL before any execution; the
preview / run pipeline lives in ``api/kpis.py`` and is unchanged. We
deliberately don't auto-run NL output.

Every run — agent or single — writes a ``kpi_nl_run`` audit row.
"""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from kpi_studio import deps
from kpi_studio.models import KpiNlRun
from kpi_studio.services import call_logger, knowledge_versions
from kpi_studio.providers.llm.base import LlmProviderError
from kpi_studio.schemas import (
    KpiSuggestionItem, KpiSuggestRequest, KpiSuggestResponse,
    NlAgentStep, NlGenerateRequest, NlGenerateResponse, NlStatusResponse,
    NlValidation,
)
from kpi_studio.services import (
    introspector, kpi_suggester, nl2sql, nl2sql_agent, settings_service,
)


def _user_id(user: Any) -> Optional[int]:
    for attr in ("user_id", "id", "userId"):
        v = getattr(user, attr, None)
        if isinstance(v, int):
            return v
    return None


def _company_id(user: Any) -> Optional[int]:
    cfg = deps.get_config()
    if cfg.tenant_resolver is None:
        return None
    try:
        return cfg.tenant_resolver(user)
    except Exception:
        return None


def _audit(
    db: Session,
    *,
    user: Any,
    surface: str,
    payload: NlGenerateRequest,
    sql: str,
    explanation: str,
    succeeded: bool,
    error: Optional[str],
    provider: str,
    model: str,
    iterations: int,
    total_tokens: int,
    duration_ms: int,
    steps: list[dict],
) -> None:
    """Best-effort audit write — never raises (audit failure must not
    break the user's request)."""
    try:
        fp = knowledge_versions.current(db)
        db.add(KpiNlRun(
            company_id=_company_id(user),
            user_id=_user_id(user),
            surface=surface,
            prompt=payload.prompt[:8000],
            final_sql=(sql or None),
            explanation=(explanation or None),
            succeeded=succeeded,
            error=(error[:200] if error else None),
            provider=provider,
            model=model,
            iterations=iterations,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            steps=steps,
            **fp.as_kwargs(),
        ))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def build_router() -> APIRouter:
    router = APIRouter()
    auth = deps.get_current_user
    db_dep = deps.get_metadata_db
    perm = deps.require_kpi_permission

    @router.get(
        "/status",
        response_model=NlStatusResponse,
        dependencies=[Depends(perm("kpi:view"))],
    )
    def status_endpoint(db: Session = Depends(db_dep)) -> NlStatusResponse:
        # Resolve at request time so a SuperAdmin's settings change is
        # reflected immediately — no uvicorn restart needed.
        # Fallback chain: DB row → env var → host-injected cfg.llm_provider.
        # The cfg fallback exists so hosts can inject a stub for tests
        # or programmatic-only setups without touching env / DB.
        eff = settings_service.get_effective(db, env=os.environ)
        provider = eff.provider or deps.get_config().llm_provider
        if provider is None:
            return NlStatusResponse(enabled=False)
        return NlStatusResponse(
            enabled=True,
            provider=getattr(provider, "name", "unknown"),
        )

    @router.post(
        "/generate",
        response_model=NlGenerateResponse,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def generate(
        payload: NlGenerateRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> NlGenerateResponse:
        cfg = deps.get_config()
        eff = settings_service.get_effective(db, env=os.environ)
        # Same fallback chain as /status — DB → env → host-injected cfg.
        provider = eff.provider or cfg.llm_provider
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": "llm_disabled",
                    "message": (
                        "No LLM provider configured. Set provider + API key "
                        "in KPI Studio → Settings, or via KPI_LLM_PROVIDER + "
                        "KPI_OPENAI_API_KEY env vars."
                    ),
                },
            )

        # Reuse the cached schema snapshot — auto-introspect on first call.
        snap = introspector.get_current_snapshot(db)
        if snap is None:
            try:
                schema_payload = introspector.reflect_schema(cfg.target_engine, cfg)
                snap = introspector.persist_snapshot(db, schema_payload)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Schema introspection failed: {exc}",
                )
        else:
            schema_payload = introspector.load_payload(snap)

        mode = (payload.mode or "agent").lower().strip()
        if mode not in ("agent", "single"):
            raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")

        # T-902: route single-shot + agent paths through their stages so
        # per-stage routing applies to /nl/generate the same way it does
        # to the chat endpoint. Single-shot path doesn't have a clean
        # stage today (it IS the entire NL→SQL surface), so it falls
        # under STAGE_AGENT_DEFAULT.
        from kpi_studio.stages import STAGE_AGENT_DEFAULT
        agent_provider = settings_service.provider_for_stage(
            eff, STAGE_AGENT_DEFAULT) or provider

        # Open call-log correlation so every LLM call fired by this
        # /nl/generate request shows up as one group in the admin UI.
        with call_logger.log_context(
            trigger_source="nl_generate",
            user_id=_user_id(user),
            company_id=_company_id(user),
            stage_key=STAGE_AGENT_DEFAULT,
        ):
            if mode == "single":
                return _run_single(payload, schema_payload, agent_provider, db, user, cfg)
            return _run_agent(payload, schema_payload, agent_provider, db, user, cfg, eff)

    @router.post(
        "/suggest-kpis",
        response_model=KpiSuggestResponse,
        dependencies=[Depends(perm("kpi:author"))],
    )
    def suggest_kpis_for_table(
        payload: KpiSuggestRequest,
        db: Session = Depends(db_dep),
        user: Any = Depends(auth),
    ) -> KpiSuggestResponse:
        """Phase J — AI proposes a set of useful KPIs for the given
        table. Each item is a fully-validated BuilderSpec the caller
        can save through the normal /kpis POST endpoint."""
        cfg = deps.get_config()
        eff = settings_service.get_effective(db, env=os.environ)
        provider = eff.provider or cfg.llm_provider
        if provider is None:
            raise HTTPException(
                status_code=503,
                detail="AI suggestions are disabled — no LLM provider is configured.",
            )

        # Re-use the cached introspection snapshot — same source of
        # truth as the schema explorer + nl2sql agent.
        snap = introspector.get_current_snapshot(db)
        if snap is None:
            try:
                schema_payload = introspector.reflect_schema(cfg.target_engine, cfg)
                introspector.persist_snapshot(db, schema_payload, created_by=_user_id(user))
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502,
                    detail=f"Schema introspection failed: {exc}",
                )
        else:
            schema_payload = introspector.load_payload(snap)

        try:
            result = kpi_suggester.suggest_kpis(
                provider=provider,
                schema=schema_payload,
                table_name=payload.table,
                table_schema=payload.schema_name,
                count=payload.count,
                max_tokens=eff.max_tokens_per_call,
            )
        except LlmProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        return KpiSuggestResponse(
            items=[
                KpiSuggestionItem(
                    name=it.name,
                    description=it.description,
                    builder_spec=it.builder_spec,
                    chart_config=it.chart_config,
                    sql=it.sql,
                )
                for it in result.items
            ],
            tokens=result.tokens,
            latency_ms=result.latency_ms,
            model=result.model,
            error=result.error,
        )

    return router


# ---------------------------------------------------------------------------
# Mode dispatch — separate functions to keep each path readable.
# ---------------------------------------------------------------------------

def _run_single(
    payload: NlGenerateRequest,
    schema_payload,
    provider,
    db: Session,
    user: Any,
    cfg,
) -> NlGenerateResponse:
    """Phase A3 one-shot path. Kept as fallback for cost-conscious callers."""
    try:
        result = nl2sql.generate_sql(
            provider=provider,
            schema=schema_payload,
            user_prompt=payload.prompt,
            dialect=("T-SQL" if cfg.target_engine.dialect.name == "mssql" else "sqlite"),
        )
    except LlmProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "llm_error", "message": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    validation = NlValidation(
        ok=result.safety is not None and result.safety_error is None,
        message=result.safety_error,
        findings=result.safety_findings or [],
        rewritten_sql=result.safety.rewritten if result.safety else None,
    )

    response = NlGenerateResponse(
        sql=result.sql,
        explanation=result.explanation,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        usage=result.usage,
        validation=validation,
        mode="single",
        steps=[],
        iterations=1,
        total_tokens=int(result.usage.get("total_tokens") or 0),
        succeeded=True,
    )
    _audit(
        db, user=user, surface="editor", payload=payload,
        sql=result.sql, explanation=result.explanation,
        succeeded=True, error=None,
        provider=result.provider, model=result.model,
        iterations=1,
        total_tokens=int(result.usage.get("total_tokens") or 0),
        duration_ms=result.latency_ms,
        steps=[],
    )
    return response


def _run_agent(
    payload: NlGenerateRequest,
    schema_payload,
    provider,
    db: Session,
    user: Any,
    cfg,
    eff: settings_service.EffectiveSettings,
) -> NlGenerateResponse:
    """Phase A7 agentic path. Drives the tool-use loop until propose_sql
    or a cap fires. Audits the full step timeline either way.

    Caps come from the resolved settings (DB → env → defaults), so a
    SuperAdmin's edits in KPI Studio → Settings take effect on the very
    next request.
    """
    try:
        agent_result = nl2sql_agent.run_agent(
            provider=provider,
            schema=schema_payload,
            target_engine=cfg.target_engine,
            db=db,
            user_prompt=payload.prompt,
            user_id=_user_id(user),
            company_id=_company_id(user),
            max_iterations=eff.max_iterations,
            token_budget=eff.token_budget,
            max_tokens_per_call=eff.max_tokens_per_call,
        )
    except LlmProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "llm_error", "message": str(exc)},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Step list → Pydantic-friendly dicts. ``asdict`` drops dataclass-only
    # methods cleanly. Then map to NlAgentStep for the response.
    step_dicts = [asdict(s) for s in agent_result.steps]
    response_steps = [NlAgentStep(**s) for s in step_dicts]

    validation = NlValidation(
        ok=agent_result.safety is not None and agent_result.safety_error is None,
        message=agent_result.safety_error,
        findings=agent_result.safety_findings or [],
        rewritten_sql=agent_result.safety.rewritten if agent_result.safety else None,
    )

    response = NlGenerateResponse(
        sql=agent_result.sql,
        explanation=agent_result.explanation,
        provider=agent_result.provider,
        model=agent_result.model,
        latency_ms=agent_result.total_latency_ms,
        usage={"total_tokens": agent_result.total_tokens},
        validation=validation,
        mode="agent",
        steps=response_steps,
        iterations=agent_result.iterations,
        total_tokens=agent_result.total_tokens,
        succeeded=agent_result.succeeded,
        error=agent_result.error,
    )

    _audit(
        db, user=user, surface="editor", payload=payload,
        sql=agent_result.sql, explanation=agent_result.explanation,
        succeeded=agent_result.succeeded, error=agent_result.error,
        provider=agent_result.provider, model=agent_result.model,
        iterations=agent_result.iterations,
        total_tokens=agent_result.total_tokens,
        duration_ms=agent_result.total_latency_ms,
        steps=step_dicts,
    )
    return response
