"""KpiStudioConfig — host wiring contract.

Everything host-shaped (auth, tenant resolution, DB engines, AI client)
flows through this object so the package stays portable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# Avoid an import cycle: config.py is imported very early; the LLM provider
# stack is loaded later. Use a TYPE_CHECKING-only import for the type hint.
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from kpi_studio.providers.llm.base import LlmProvider


# Re-typed loosely so we never import host symbols here.
AuthDep = Callable[..., Any]
TenantResolver = Callable[[Any], Optional[int]]
PermissionChecker = Callable[[Any, str], bool]


@dataclass
class KpiStudioConfig:
    """Configuration injected by the host application."""

    # ---- required ---------------------------------------------------------
    auth_dep: AuthDep
    """FastAPI dependency that returns the current user. Used by every endpoint."""

    metadata_session_factory: sessionmaker
    """Session factory for the *metadata* DB (where kpi_* tables live).

    In single-DB hosts this is the same as the host's SessionLocal.
    """

    target_engine: Engine
    """The DB engine pointing at the schema we want to introspect / query.

    Phase 1 uses this only for read-only metadata reflection. Phase 2 will
    add a separate ``readonly_engine`` for actual query execution.
    """

    # ---- optional ---------------------------------------------------------
    tenant_resolver: Optional[TenantResolver] = None
    """Maps the current user object to a tenant id (e.g. company_id).

    Return ``None`` for single-tenant hosts. Used to scope KPI ownership
    and (in later phases) to inject tenant predicates.
    """

    permission_checker: Optional[PermissionChecker] = None
    """Optional ``(user, required_permission_code) -> bool`` callback.

    If ``None``, every authenticated user is treated as a KPI admin.
    Wire to your RBAC layer to enforce ``kpi:view`` / ``kpi:author`` /
    ``kpi:admin``.
    """

    llm_provider: Optional["LlmProvider"] = None
    """Optional NL→SQL provider. ``None`` disables the chatbot + NL endpoints
    entirely; manual SQL authoring still works. Build this with
    ``kpi_studio.providers.llm.build_provider_from_env(os.environ)`` or pass
    a custom implementation."""

    table_prefix: str = "kpi_"
    """Prefix applied to every table the package owns. Change if it
    collides with host tables — but rebuild migrations after."""

    excluded_schemas: Sequence[str] = field(
        default_factory=lambda: (
            # SQL Server system schemas + the package's own tables.
            "sys", "INFORMATION_SCHEMA", "guest", "db_owner", "db_accessadmin",
            "db_securityadmin", "db_ddladmin", "db_backupoperator",
            "db_datareader", "db_datawriter", "db_denydatareader",
            "db_denydatawriter",
        )
    )
    """Schemas hidden from the introspector. Always denies system schemas."""

    excluded_table_patterns: Sequence[str] = field(
        default_factory=lambda: ("kpi_", "alembic_", "sysdiagrams")
    )
    """Tables hidden from the introspector. Patterns are *prefix* matches
    against the bare table name (case-insensitive). Defaults hide the
    package's own tables and Alembic bookkeeping."""

    schema_cache_ttl_seconds: int = 3600
    """How long an introspected schema snapshot stays warm in memory."""

    def is_table_visible(self, table_name: str) -> bool:
        """True if a table should appear in the introspected schema."""
        lower = table_name.lower()
        return not any(
            lower.startswith(p.lower()) for p in self.excluded_table_patterns
        )
