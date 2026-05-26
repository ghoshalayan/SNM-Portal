"""Router factory — the public entry point of kpi_studio.

The host calls ``create_router(config)``; we bind the config into module
state, rewrite the auth dep so FastAPI's DI sees the host's real signature,
and return a single ``APIRouter`` with all sub-routers mounted.
"""
from __future__ import annotations

from fastapi import APIRouter

from kpi_studio import deps
from kpi_studio.api import call_logs as call_logs_api
from kpi_studio.api import chat as chat_api
from kpi_studio.api import dashboards as dashboards_api
from kpi_studio.api import eval as eval_api
from kpi_studio.api import jobs as jobs_api
from kpi_studio.api import kpis as kpis_api
from kpi_studio.api import nl as nl_api
from kpi_studio.api import providers as providers_api
from kpi_studio.api import schema as schema_api
from kpi_studio.api import settings as settings_api
from kpi_studio.config import KpiStudioConfig


def create_router(config: KpiStudioConfig) -> APIRouter:
    """Build a kpi_studio APIRouter wired to the given config.

    Sub-routers are built *after* ``bind_config`` so each ``Depends(...)``
    captures the live host auth dep instead of the module-level placeholder.
    """
    deps.bind_config(config)
    deps.get_current_user = config.auth_dep  # type: ignore[assignment]

    router = APIRouter(tags=["KPI Studio"])

    # No-auth health probe so an operator can ``curl
    # http://<host>/api/v1/kpi/healthz`` to confirm the module mounted.
    # Returning 404 here means the host failed to mount the router (and
    # the uvicorn logs will have the import error). Returning 200 means
    # the failure is downstream — auth, DB, or the user's permission.
    @router.get("/healthz", tags=["KPI Studio"])
    def healthz():
        return {
            "ok": True,
            "module": "kpi_studio",
            "llm_provider": getattr(config.llm_provider, "name", None) if config.llm_provider else None,
        }

    router.include_router(schema_api.build_router(), prefix="/schema")
    router.include_router(kpis_api.build_router(), prefix="/kpis")
    router.include_router(dashboards_api.build_router(), prefix="/dashboards")
    router.include_router(nl_api.build_router(), prefix="/nl")
    router.include_router(settings_api.build_router(), prefix="/settings")
    # Multi-provider sub-router. Mounted under /settings/providers so the
    # admin UI's "Providers" tab is a logical sub-resource of settings.
    router.include_router(providers_api.build_router(),
                          prefix="/settings/providers")
    # Read-only observability — every outbound LLM HTTP call recorded
    # with full request/response JSON, grouped by correlation_id.
    router.include_router(call_logs_api.build_router(),
                          prefix="/settings/call-logs")
    router.include_router(chat_api.build_router(), prefix="/chat")
    router.include_router(eval_api.build_router(), prefix="/eval")
    router.include_router(jobs_api.build_router(), prefix="/jobs")
    return router
