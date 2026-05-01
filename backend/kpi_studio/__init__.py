"""KPI Studio — pluggable analytics module.

Drop-in FastAPI module providing:
  * Schema explorer (Phase 1 — current)
  * SQL-authored KPIs                    (Phase 2)
  * Dashboards                           (Phase 3)
  * Natural-language → SQL via Claude    (Phase 4)
  * Parameterised KPIs, scheduled refresh (Phase 5)

Host wiring:

    from kpi_studio import create_router, KpiStudioConfig

    app.include_router(
        create_router(KpiStudioConfig(
            auth_dep=get_current_user,
            tenant_resolver=lambda u: u.company_id,
            metadata_session_factory=SessionLocal,
            target_engine=engine,
        )),
        prefix="/api/v1/kpi",
    )

The package owns its own tables (prefix ``kpi_``) and its own Alembic
migrations under ``kpi_studio/alembic/``. It must stay free of host-specific
imports — anything host-shaped flows through ``KpiStudioConfig``.
"""
from kpi_studio.config import KpiStudioConfig
from kpi_studio.router import create_router

__all__ = ["KpiStudioConfig", "create_router"]
__version__ = "0.1.0"
