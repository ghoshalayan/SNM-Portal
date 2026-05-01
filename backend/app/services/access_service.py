"""Unified Access Control Service (RBAC v2).

Implements the 7-filter access pipeline:
  F1 Auth              - handled by get_current_user dependency
  F2 Company           - multi-tenant isolation
  F3 Menu Permission   - RoleMenuMap (canRead/Add/Edit/Delete + custom actions)
  F4 Parent Visibility - for sub-resources (helper require_parent_visible)
  F5 Hierarchy         - ownerUserId in visible_user_ids (BFS on reportTo + peers)
  F6 Location          - record's (state, dist) in user's allotted locations
  F7 Business Rule     - entity-specific (FY exists, status transitions, etc.)

Bypass matrix:
  SuperAdmin   → bypasses F2-F6 (still hits F1, F7)
  CompanyAdmin → bypasses F5 and F6 (obeys F1-F4, F7)
  Others       → all filters enforced

All business modules route through AccessContext and the helpers below.
No role-name strings are checked anywhere — behavior derives from Role flags
and RoleMenuMap flags (fully dynamic / DB-driven).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Set, Tuple

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core import cache, cache_keys
from app.models.user import UserRoleMap
from app.models.user_location_map import UserLocationMap
from app.models.location import StateMaster, DistrictMaster
from app.models.role import Role
from app.models.role_menu_map import RoleMenuMap
from app.models.menu import MenuMaster


# -------------------------------------------------------------------------
# LocationAccess (kept here so access_service is self-contained)
# -------------------------------------------------------------------------

class LocationAccess:
    """Holds a user's resolved location jurisdiction."""

    def __init__(self, bypass: bool = False):
        self.bypass = bypass  # True = see all locations (SuperAdmin/CompanyAdmin/locationScopeRequired=False)
        self._full_states: Set[str] = set()
        self._specific: Set[Tuple[str, str]] = set()
        self._all_states_original: Set[str] = set()

    def _add_full_state(self, state: str):
        self._full_states.add(state.strip().lower())
        self._all_states_original.add(state.strip())

    def _add_district(self, state: str, dist: str):
        self._specific.add((state.strip().lower(), dist.strip().lower()))
        self._all_states_original.add(state.strip())

    def can_access(self, state: Optional[str], dist: Optional[str]) -> bool:
        if self.bypass:
            return True
        if not state:
            return True  # no location on record — allow
        sl = state.strip().lower()
        if sl in self._full_states:
            return True
        if dist:
            return (sl, dist.strip().lower()) in self._specific
        return False

    def build_sql_filter(self, state_col, dist_col, nullable_fk=None):
        """Return a SQLAlchemy filter or None (no filter) or False (no access)."""
        if self.bypass:
            return None

        conditions = []
        if nullable_fk is not None:
            conditions.append(nullable_fk == None)  # noqa: E711

        if self._full_states:
            full_state_names = {
                s for s in self._all_states_original
                if s.strip().lower() in self._full_states
            }
            if full_state_names:
                conditions.append(state_col.in_(full_state_names))

        for s_lower, d_lower in self._specific:
            for orig_s in self._all_states_original:
                if orig_s.strip().lower() == s_lower:
                    conditions.append(
                        (state_col == orig_s) & (dist_col.ilike(d_lower))
                    )
                    break

        if not conditions:
            return False  # deny everything

        return or_(*conditions)


# -------------------------------------------------------------------------
# AccessContext — single source of truth for a request
# -------------------------------------------------------------------------

@dataclass
class AccessContext:
    """All access info for the current request, computed once per request."""

    user_id: int
    company_id: int
    role_id: int
    is_super_admin: bool
    is_company_admin: bool = False
    role: Optional[Role] = None
    # None = no hierarchy filter (SuperAdmin / CompanyAdmin / scope-free role)
    visible_user_ids: Optional[Set[int]] = None
    location: LocationAccess = field(default_factory=lambda: LocationAccess(bypass=True))
    # Cache permission map for this request (menuName -> perm row)
    _perm_cache: dict = field(default_factory=dict)
    _db: Optional[Session] = None

    # ---- F3: Menu permissions ----
    def has_permission(self, menu_name: str, action: str) -> bool:
        """Check RoleMenuMap for (menu, action).
        SuperAdmin always True. CompanyAdmin obeys menu perms (per business rule).
        Action names (case-sensitive): CanAdd, CanRead, CanEdit, CanDelete,
        CanApprove, CanRevise, CanTransferOwnership, CanGenerateUnderOthers,
        CanEditNumber, CanExport.
        """
        if self.is_super_admin:
            return True
        perm = self._get_menu_perm(menu_name)
        if not perm:
            return False
        return bool(getattr(perm, action, False))

    def _get_menu_perm(self, menu_name: str):
        # L1 cache: per-request (avoids re-query within one endpoint)
        if menu_name in self._perm_cache:
            return self._perm_cache[menu_name]
        if not self._db:
            return None

        # L2 cache: process-wide TTL (shared across requests)
        ck = cache_keys.role_perm(self.role_id, menu_name)
        hit, cached_perm = cache.cache_get_ex("role_perms", ck)
        if hit:
            self._perm_cache[menu_name] = cached_perm
            return cached_perm

        mapping = (
            self._db.query(RoleMenuMap)
            .join(MenuMaster, RoleMenuMap.menuId == MenuMaster.menuId)
            .filter(
                RoleMenuMap.roleId == self.role_id,
                MenuMaster.menuName == menu_name,
                RoleMenuMap.isActive == True,
            )
            .first()
        )
        # Detach so cached object survives session close
        if mapping is not None:
            self._db.expunge(mapping)
        cache.cache_set("role_perms", ck, mapping)
        self._perm_cache[menu_name] = mapping
        return mapping

    # ---- F5: Hierarchy ----
    def can_see_user(self, target_user_id: Optional[int]) -> bool:
        """Check if target user's records are visible to current user."""
        if self.visible_user_ids is None:
            return True  # no filter = see all
        if target_user_id is None:
            return True  # no owner = no hierarchy filter (e.g. legacy data)
        return target_user_id in self.visible_user_ids

    # ---- F6: Location ----
    def can_access_location(self, state: Optional[str], dist: Optional[str]) -> bool:
        return self.location.can_access(state, dist)


# -------------------------------------------------------------------------
# Context builder — ONE query pass per request
# -------------------------------------------------------------------------

def _build_visible_user_ids(
    db: Session,
    user_id: int,
    company_id: int,
    role: Optional[Role],
) -> Optional[Set[int]]:
    """BFS on UserRoleMap.reportTo applying Role flags:
      - downwardLevels (N levels down, -1 = unlimited)
      - upwardLevels (N levels up, -1 = unlimited, 0 = none)
      - includeSubtreeOnUpward (when walking up, add each ancestor's subtree)
      - peerAccess (siblings at same reportTo)
      - peerSubtree (if peerAccess, also peers' subtrees)
    Returns None = no filter (sees all).
    """
    if role is None:
        # Unassigned user — only own records
        return {user_id}

    # Safe access to new flags (default values if column not yet migrated)
    downward_levels = getattr(role, "downwardLevels", -1)
    upward_levels = getattr(role, "upwardLevels", role.upwardVisibilityLevels or 0)
    include_subtree_on_upward = getattr(role, "includeSubtreeOnUpward", True)
    peer_access = bool(role.peerAccess)
    peer_subtree = getattr(role, "peerSubtree", False)

    # Build parent→children map for this company
    rows = (
        db.query(UserRoleMap.userId, UserRoleMap.reportTo)
        .filter(UserRoleMap.companyId == company_id, UserRoleMap.isActive == True)
        .all()
    )
    children_map: dict[int, set[int]] = {}
    user_parent: dict[int, int] = {}
    for uid, report_to in rows:
        if report_to is not None and report_to != uid:
            children_map.setdefault(report_to, set()).add(uid)
            user_parent[uid] = report_to

    visible: Set[int] = {user_id}

    # --- Downward (N levels, -1 = unlimited) ---
    if downward_levels != 0:
        queue = deque([(user_id, 0)])
        while queue:
            node, depth = queue.popleft()
            if downward_levels > 0 and depth >= downward_levels:
                continue
            for child in children_map.get(node, set()):
                if child not in visible:
                    visible.add(child)
                    queue.append((child, depth + 1))

    # --- Upward (N levels, -1 = unlimited, 0 = none) ---
    if upward_levels != 0:
        current = user_id
        levels_walked = 0
        while True:
            parent = user_parent.get(current)
            if parent is None:
                break
            visible.add(parent)
            if include_subtree_on_upward:
                sub_queue = deque([parent])
                while sub_queue:
                    node = sub_queue.popleft()
                    for child in children_map.get(node, set()):
                        if child not in visible:
                            visible.add(child)
                            sub_queue.append(child)
            levels_walked += 1
            if upward_levels > 0 and levels_walked >= upward_levels:
                break
            current = parent

    # --- Peers (siblings at same reportTo) ---
    if peer_access:
        my_parent = user_parent.get(user_id)
        if my_parent is not None:
            for sibling in children_map.get(my_parent, set()):
                if sibling == user_id or sibling in visible:
                    continue
                visible.add(sibling)
                if peer_subtree:
                    sub_queue = deque([sibling])
                    while sub_queue:
                        node = sub_queue.popleft()
                        for child in children_map.get(node, set()):
                            if child not in visible:
                                visible.add(child)
                                sub_queue.append(child)

    return visible


def _build_location_access(
    db: Session,
    user_id: int,
    company_id: int,
    role: Optional[Role],
    bypass: bool,
) -> LocationAccess:
    """Load user's allotted locations. Bypass=True → see all."""
    access = LocationAccess(bypass=bypass)
    if bypass:
        return access

    # Respect locationScopeRequired — if False, bypass location filter
    if role and not role.locationScopeRequired:
        access.bypass = True
        return access

    mappings = (
        db.query(StateMaster.StateName, DistrictMaster.districName)
        .select_from(UserLocationMap)
        .join(StateMaster, StateMaster.stateid == UserLocationMap.stateid)
        .outerjoin(DistrictMaster, DistrictMaster.districtid == UserLocationMap.districtid)
        .filter(
            UserLocationMap.userId == user_id,
            UserLocationMap.companyId == company_id,
            UserLocationMap.isActive == True,
        )
        .all()
    )
    for state_name, district_name in mappings:
        if not district_name:
            access._add_full_state(state_name)
        else:
            access._add_district(state_name, district_name)

    return access


def build_access_context(db: Session, user: CurrentUser) -> AccessContext:
    """Build the AccessContext for this request (called once per endpoint).

    Cached layers:
    - Role object (10 min TTL) — keyed by role_id
    - visible_user_ids (5 min TTL) — keyed by (company_id, user_id)
    - LocationAccess (5 min TTL) — keyed by (company_id, user_id)

    Invalidation happens automatically when the underlying write endpoints
    call the helpers in `cache_invalidation.py`.
    """
    # --- Role lookup (cached) ---
    role: Optional[Role] = None
    if user.role_id:
        rkey = cache_keys.role_settings(user.role_id)
        hit, cached_role = cache.cache_get_ex("role_settings", rkey)
        if hit:
            role = cached_role
        else:
            role = db.query(Role).filter(Role.roleId == user.role_id).first()
            # Detach from session so cached object survives session close
            if role is not None:
                db.expunge(role)
            cache.cache_set("role_settings", rkey, role)

    is_company_admin = bool(getattr(role, "IsCompanyAdmin", False)) if role else False

    # --- Visibility + Location (cached) ---
    if user.is_super_admin or is_company_admin:
        visible_ids = None
        loc = LocationAccess(bypass=True)
    else:
        # visible_user_ids
        vkey = cache_keys.visibility(user.user_id, user.company_id)
        vhit, cached_ids = cache.cache_get_ex("visibility", vkey)
        if vhit:
            visible_ids = cached_ids
        else:
            visible_ids = _build_visible_user_ids(db, user.user_id, user.company_id, role)
            cache.cache_set("visibility", vkey, visible_ids)

        # LocationAccess
        lkey = cache_keys.location_access(user.user_id, user.company_id)
        lhit, cached_loc = cache.cache_get_ex("location", lkey)
        if lhit:
            loc = cached_loc
        else:
            loc = _build_location_access(db, user.user_id, user.company_id, role, bypass=False)
            cache.cache_set("location", lkey, loc)

    return AccessContext(
        user_id=user.user_id,
        company_id=user.company_id,
        role_id=user.role_id,
        is_super_admin=user.is_super_admin,
        is_company_admin=is_company_admin,
        role=role,
        visible_user_ids=visible_ids,
        location=loc,
        _db=db,
    )


def get_access_context(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AccessContext:
    """FastAPI dependency — use in endpoint signatures:
        ctx: AccessContext = Depends(get_access_context)
    """
    return build_access_context(db, current_user)


# -------------------------------------------------------------------------
# Filter helpers — apply to SQLAlchemy queries
# -------------------------------------------------------------------------

def apply_company_filter(query, company_col, ctx: AccessContext):
    """F2 Company isolation (SuperAdmin bypasses)."""
    if ctx.is_super_admin:
        return query
    return query.filter(company_col == ctx.company_id)


def apply_hierarchy_filter(query, owner_col, ctx: AccessContext, allow_null: bool = True):
    """F5 Hierarchy — restrict to visible owners.
    If allow_null=True, records with NULL ownerUserId are included (legacy/unassigned).
    """
    if ctx.visible_user_ids is None:
        return query  # no filter
    if not ctx.visible_user_ids:
        # Empty set — deny everything
        return query.filter(False)
    if allow_null:
        return query.filter(or_(owner_col.in_(ctx.visible_user_ids), owner_col == None))  # noqa: E711
    return query.filter(owner_col.in_(ctx.visible_user_ids))


def apply_location_filter(query, state_col, dist_col, ctx: AccessContext, nullable_fk=None):
    """F6 Location — restrict by state/district. nullable_fk = allow records
    with NULL FK (e.g. siteId) through."""
    filt = ctx.location.build_sql_filter(state_col, dist_col, nullable_fk=nullable_fk)
    if filt is None:
        return query
    if filt is False:
        return query.filter(False)
    return query.filter(filt)


# -------------------------------------------------------------------------
# Single-record validators (raise 403 on denial)
# -------------------------------------------------------------------------

def require_permission(menu_name: str, action: str, ctx: AccessContext):
    """F3 — raise 403 if user lacks permission."""
    if not ctx.has_permission(menu_name, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {action} on {menu_name}",
        )


def require_owner_visible(owner_user_id: Optional[int], ctx: AccessContext):
    """F5 — raise 403 if record's owner is outside current user's visibility."""
    if not ctx.can_see_user(owner_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have visibility to this record's owner",
        )


def require_location_access(
    state: Optional[str],
    dist: Optional[str],
    ctx: AccessContext,
    detail: str = "You do not have access to this location",
):
    """F6 — raise 403 if user cannot access the record's location."""
    if not ctx.can_access_location(state, dist):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_parent_visible(parent, ctx: AccessContext):
    """F4 — parent record must pass F5 (hierarchy) for the current user.
    Call this for sub-resources (enquiry details, quotation TnC, etc.).
    Pass the parent ORM object; function reads .ownerUserId.
    """
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent record not found")
    owner_user_id = getattr(parent, "ownerUserId", None)
    if owner_user_id is None:
        return  # no owner on parent — nothing to check
    require_owner_visible(owner_user_id, ctx)
