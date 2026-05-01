"""FastAPI deps wired from the host-injected ``KpiStudioConfig``.

The router holds a single config instance; this module exposes deps that
read from it. Doing it this way keeps the router file small and lets
endpoints declare their dependencies via ``Annotated`` aliases.
"""
from __future__ import annotations

from typing import Any, Generator

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from kpi_studio.config import KpiStudioConfig

# The router writes the active config here at import time. Endpoints read
# it through the deps below. Module-global is fine: a process only ever
# mounts one KPI router instance.
_config: KpiStudioConfig | None = None


def bind_config(cfg: KpiStudioConfig) -> None:
    global _config
    _config = cfg


def get_config() -> KpiStudioConfig:
    if _config is None:  # pragma: no cover — only happens if router never mounted
        raise RuntimeError("KpiStudioConfig not bound. Call create_router() first.")
    return _config


def get_metadata_db() -> Generator[Session, None, None]:
    """Session into the DB where kpi_* tables live."""
    cfg = get_config()
    session = cfg.metadata_session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(*args, **kwargs) -> Any:  # pragma: no cover — replaced at runtime
    """Placeholder. ``create_router`` rewrites this to delegate to
    ``cfg.auth_dep`` so FastAPI's dependency-injection sees the real signature."""
    raise NotImplementedError


def require_kpi_permission(code: str):
    """Dep factory: enforces a permission via host-supplied checker.

    If the host didn't supply one, we fall back to "any authenticated user
    can do anything" — fine for Phase 1 (read-only schema browsing).
    """
    def _check(user: Any = Depends(get_current_user)) -> Any:
        cfg = get_config()
        if cfg.permission_checker is None:
            return user
        if not cfg.permission_checker(user, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {code}",
            )
        return user
    return _check
