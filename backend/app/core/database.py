"""Database singletons — lazy-initialised so the module imports cleanly
even when the DB is unreachable (CI without a SQL Server box, unit tests
that only exercise pure logic, etc.).

- ``Base`` is declared eagerly so every model file can ``from
  app.core.database import Base`` at import time without touching the
  network.
- ``engine`` and ``SessionLocal`` are lazily constructed on first
  attribute access via PEP 562 module-level ``__getattr__``. Production
  paths (``main.py`` on startup, ``dependencies.get_db`` on first
  request) trigger initialisation transparently; unit tests that never
  reference them never pay the cost.
"""
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models. Defined eagerly because
    every ``app.models.*`` module imports it at module-load time."""
    pass


# Lazy singletons — guarded behind PEP 562 ``__getattr__`` below.
_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _build_engine() -> Engine:
    """Construct the SQLAlchemy engine. Called at most once per process.

    sqlite uses ``SingletonThreadPool`` which doesn't accept
    ``pool_size`` / ``max_overflow``; the connection-pool tuning only
    matters for the production SQL Server backend. Strip those when
    the DSN is sqlite (matters in unit-test envs that point at
    ``sqlite:///:memory:``)."""
    dsn = settings.DB_CONNECTION_STRING or ""
    kwargs: dict[str, Any] = {"pool_pre_ping": True, "echo": settings.DEBUG}
    if not dsn.startswith("sqlite"):
        kwargs.update(pool_size=10, max_overflow=20)
    return create_engine(dsn, **kwargs)


def get_engine() -> Engine:
    """Public accessor for callers that prefer an explicit function over
    the module attribute (also handy for type-checkers)."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_local() -> sessionmaker:
    """Public accessor for the sessionmaker factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine(),
        )
    return _SessionLocal


def __getattr__(name: str) -> Any:
    """Module-level ``__getattr__`` (PEP 562). Lets legacy callers keep
    using ``from app.core.database import engine`` / ``SessionLocal``
    while we move new code toward the explicit ``get_engine()`` /
    ``get_session_local()`` accessors. Unit tests that don't touch the
    DB never trigger initialisation."""
    if name == "engine":
        return get_engine()
    if name == "SessionLocal":
        return get_session_local()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
