"""Centralized cache key builders.

Keep all cache keys defined in one place so invalidation code and read code
never disagree. Every function returns a string key; callers use it with
cache_get / cache_set / invalidate.

Format conventions:
- Colon-separated segments: {scope}:{company_id}:{user_id}:{extra}
- Always include company_id when data is company-scoped
- No user-provided strings unless validated — keys are always ints/enums
"""


# --- Visibility (org-tree BFS results) ---------------------------------

def visibility(user_id: int, company_id: int) -> str:
    return f"{company_id}:{user_id}"


def visibility_prefix_for_company(company_id: int) -> str:
    """For invalidating all visibility entries in a company."""
    return f"{company_id}:"


# --- Location access --------------------------------------------------

def location_access(user_id: int, company_id: int) -> str:
    return f"{company_id}:{user_id}"


def location_prefix_for_company(company_id: int) -> str:
    return f"{company_id}:"


# --- Role / menu permissions ------------------------------------------

def role_perm(role_id: int, menu_name: str) -> str:
    return f"{role_id}:{menu_name}"


def role_perm_prefix_for_role(role_id: int) -> str:
    return f"{role_id}:"


def role_settings(role_id: int) -> str:
    return f"role:{role_id}"


def menu_tree(role_id: int, company_id: int) -> str:
    return f"{company_id}:{role_id}"


# --- Master data ------------------------------------------------------

def master(entity: str, company_id: int) -> str:
    """entity is the master endpoint suffix, e.g. 'item-grades', 'countries'."""
    return f"{entity}:{company_id}"


def master_prefix_for_entity(entity: str) -> str:
    return f"{entity}:"


# --- Company ----------------------------------------------------------

def company(company_id: int) -> str:
    return f"company:{company_id}"
