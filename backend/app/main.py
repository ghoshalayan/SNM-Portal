from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.core.config import settings
from app.api.v1.router import api_router
from app.core.error_handler import (
    RequestIdMiddleware,
    StarletteHTTPException,
    http_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging_config import configure_logging
from app.core.slow_query_middleware import SlowQueryMiddleware
from app.core.database import engine, SessionLocal
from app.core.dependencies import get_current_user
from kpi_studio import KpiStudioConfig, create_router as create_kpi_router


def create_app() -> FastAPI:
    # Initialise structured logging once at app boot. Idempotent — if
    # uvicorn is configured separately the handler list stays clean.
    configure_logging()

    # Gate OpenAPI docs behind DEBUG so production doesn't expose the schema /
    # verbose traceback surface to the public internet.
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        redirect_slashes=False,
    )

    # Phase 0 error boundary — every request gets a UUID, every error
    # response gets a uniform { code, message, requestId } JSON shape,
    # every unhandled exception lands in the structured log with
    # request context for triage.
    #
    # Order matters: RequestIdMiddleware must wrap the others so the
    # request_id is on the request state before any later middleware /
    # handler reads it.
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # CORS — pull origins from settings (CORS_ORIGINS env var, comma-separated).
    # `allow_origins=["*"]` is incompatible with `allow_credentials=True` per
    # the CORS spec; browsers will silently strip credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Slow-query monitor (threshold from env; default 2000ms)
    app.add_middleware(SlowQueryMiddleware)

    # Include API router
    app.include_router(api_router)

    # KPI Studio — pluggable analytics module. Phase 1 ships the
    # SuperAdmin-only schema explorer; the executor engine falls back to
    # the main DB until KPI_DSN is configured (see kpisetup.md).
    _mount_kpi_studio(app)

    # When FILE_STORAGE_MODE=local, ensure the upload root exists. We do NOT
    # expose it as a `StaticFiles` mount: that would let any caller (even
    # unauthenticated) browse `/local-files/<uuid>` and bypass the per-asset
    # tenant + parent-entity checks enforced in `/api/v1/assets/{id}/download`.
    # The `/local-files/...` URL stored in `Asset.fileUrl` is now an internal
    # marker only — `_extract_blob_path` parses it back into a blob name when
    # the auth-checked download endpoint streams the file.
    if settings.FILE_STORAGE_MODE == "local":
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)

    @app.get("/health")
    def health_check():
        return {"status": "healthy", "app": settings.APP_NAME}

    # Start the background TP Cost scheduler (runs at midnight IST daily)
    from app.services.tp_cost_background import start_scheduler
    start_scheduler(app)

    return app


def _mount_kpi_studio(app: FastAPI) -> None:
    """Mount the kpi_studio router with host-injected wiring."""
    import os
    from sqlalchemy import create_engine
    from kpi_studio.providers.llm import build_provider_from_env

    # Phase 1 only reads catalog metadata, so reusing the main engine when
    # KPI_DSN is unset is safe. Production guidance (kpisetup.md) is to set
    # KPI_DSN to a read-only login before A3 ships, since LLM-generated SQL
    # is the larger attack surface.
    if settings.KPI_DSN:
        target_engine = create_engine(settings.KPI_DSN, pool_pre_ping=True)
    else:
        target_engine = engine

    # NL→SQL provider — None when KPI_LLM_PROVIDER is blank or its key is
    # missing. The /nl endpoints return 503 in that case; manual SQL still
    # works.
    llm_provider = build_provider_from_env(os.environ)

    # KPI Studio permissions:
    #   kpi:view     → any authenticated user (data is filtered to dashboards
    #                  they own / are assigned / company-shared via _scope_query)
    #   kpi:author   → SuperAdmin only — authoring KPIs and managing dashboards
    #   kpi:admin    → SuperAdmin only
    #   kpi:schema   → SuperAdmin only (schema-explorer diagnostic)
    #   kpi:settings → SuperAdmin only (LLM provider, API key, agent caps)
    #
    # The menu visibility (sidebar) is still SuperAdmin-only via RoleMenuMap.
    # Non-SuperAdmin users access their assigned KPI dashboards from the
    # main /dashboard home page tiles instead of the sidebar.
    def _check_permission(user, code: str) -> bool:
        is_super = bool(getattr(user, "is_super_admin", False))
        if is_super:
            return True
        # Read-only access for everyone else; assignment / scope filtering
        # at the SQL layer keeps them from seeing dashboards they shouldn't.
        return code == "kpi:view"

    kpi_router = create_kpi_router(KpiStudioConfig(
        auth_dep=get_current_user,
        metadata_session_factory=SessionLocal,
        target_engine=target_engine,
        tenant_resolver=lambda u: getattr(u, "company_id", None),
        permission_checker=_check_permission,
        llm_provider=llm_provider,
    ))
    app.include_router(kpi_router, prefix="/api/v1/kpi")

    # Loud confirmation in the uvicorn log so operators can spot startup
    # failures vs. silent under-counts. ``llm`` shows which (if any) NL
    # provider is wired.
    route_count = sum(1 for _ in kpi_router.routes)
    llm_label = getattr(llm_provider, "name", None) if llm_provider else "disabled"
    print(
        f"[kpi_studio] mounted {route_count} routes at /api/v1/kpi  "
        f"(target_engine={target_engine.url.drivername}, llm={llm_label})",
        flush=True,
    )

    # T-003 — start the in-process scheduler in this worker process.
    # Imports here (not at top) so kpi_studio's deps.bind_config() has
    # already run via create_kpi_router above. The scheduler reads
    # KPI_SCHEDULER_ENABLED to no-op in tests or in multi-worker
    # deployments where only one worker should own the schedule. The
    # scheduled_jobs import has the side-effect of registering every
    # declared job; ordering matters — registration must precede start.
    from kpi_studio.services import scheduler as kpi_scheduler
    from kpi_studio.services import scheduled_jobs  # noqa: F401 — register side-effect

    @app.on_event("startup")
    def _start_kpi_scheduler() -> None:
        try:
            kpi_scheduler.start_scheduler()
        except Exception as exc:
            # Scheduler failures must not break the API. A degraded
            # scheduler still surfaces in the admin UI's run history
            # (no recent runs = visible problem).
            print(f"[kpi_studio] scheduler start failed: {exc}", flush=True)

    @app.on_event("shutdown")
    def _stop_kpi_scheduler() -> None:
        kpi_scheduler.shutdown_scheduler()


app = create_app()
