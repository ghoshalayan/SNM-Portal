"""Cache invalidation hooks.

Called from write endpoints to invalidate relevant cache entries after
data mutations. Each function handles one type of write event.

Rule: be aggressive on invalidation (clear more than needed) rather
than risk stale data. Cache rebuild is cheap (~50ms); stale security
data is a security bug.
"""

from app.core import cache, cache_keys


def on_user_role_change(user_id: int, company_id: int) -> None:
    """User's role or reportTo changed — invalidate visibility for EVERYONE
    in the company (since any user's reportTo affects others' visibility
    via upward/peer/children traversal).
    """
    cache.invalidate_prefix("visibility", cache_keys.visibility_prefix_for_company(company_id))
    # Location may depend on role (locationScopeRequired flag) — blow it too
    cache.invalidate_prefix("location", cache_keys.location_prefix_for_company(company_id))


def on_user_location_change(user_id: int, company_id: int) -> None:
    """User's location mappings changed. Only affects that user's LocationAccess,
    but KRO cascade may affect subordinates — safe bet: invalidate company-wide."""
    cache.invalidate_prefix("location", cache_keys.location_prefix_for_company(company_id))


def on_role_change(role_id: int) -> None:
    """Role flags or menu permissions changed — invalidate the role's
    settings object AND all per-menu permission lookups for it.
    Also invalidate all visibility (role flags like peerAccess/downwardLevels
    affect BFS output)."""
    cache.invalidate("role_settings", cache_keys.role_settings(role_id))
    cache.invalidate_prefix("role_perms", cache_keys.role_perm_prefix_for_role(role_id))
    # Visibility depends on role flags; invalidate everything (cheap on write path)
    cache.invalidate_namespace("visibility")
    cache.invalidate_namespace("location")


def on_role_menu_change(role_id: int) -> None:
    """RoleMenuMap (permissions) changed — invalidate perm lookups + menu tree."""
    cache.invalidate_prefix("role_perms", cache_keys.role_perm_prefix_for_role(role_id))
    cache.invalidate_namespace("menu_tree")


def on_master_change(entity: str, company_id: int) -> None:
    """Master data CRUD — invalidate that entity for that company."""
    cache.invalidate("master", cache_keys.master(entity, company_id))


def on_company_change(company_id: int) -> None:
    """Company settings changed — invalidate company cache."""
    cache.invalidate("company", cache_keys.company(company_id))
