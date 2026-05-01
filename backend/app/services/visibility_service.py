"""Org-tree based visibility: determines which users' records the current user can see.

Rules:
- SuperAdmin → sees ALL records (no filter)
- locationScopeRequired=False → sees all records in company
- Regular user → own + all transitive subordinates (downward)
- upwardVisibilityLevels > 0 → also sees N levels of ancestors' records
- upwardVisibilityLevels = -1 → unlimited upward visibility
- peerAccess=True → also siblings (same reportTo) + their subordinates
- Unassigned user → only own records

reportTo is company-scoped via UserRoleMap.reportTo.
"""

from collections import deque
from typing import Optional, Set
from sqlalchemy.orm import Session

from app.models.user import UserRoleMap
from app.models.role import Role


def get_visible_user_ids(
    db: Session,
    user_id: int,
    company_id: int,
    is_super_admin: bool,
    role_id: int = None,
) -> Optional[Set[int]]:
    """Return set of user IDs whose records the current user can view.
    Returns None for SuperAdmins or roles with locationScopeRequired=False.
    """
    if is_super_admin:
        return None

    # Check role properties
    peer_access = False
    upward_levels = 0
    if role_id:
        role = db.query(
            Role.peerAccess, Role.locationScopeRequired, Role.upwardVisibilityLevels,
        ).filter(Role.roleId == role_id).first()
        if role:
            if not role.locationScopeRequired:
                return None  # Company admin — sees everything
            peer_access = role.peerAccess
            upward_levels = role.upwardVisibilityLevels

    rows = (
        db.query(UserRoleMap.userId, UserRoleMap.reportTo)
        .filter(UserRoleMap.companyId == company_id, UserRoleMap.isActive == True)
        .all()
    )

    # Build parent→children map and user→parent map
    children_map: dict[int, set[int]] = {}
    user_parent: dict[int, int] = {}
    for uid, report_to in rows:
        if report_to is not None and report_to != uid:
            children_map.setdefault(report_to, set()).add(uid)
            user_parent[uid] = report_to

    # --- 1. Self + downward (all transitive subordinates) ---
    visible = {user_id}
    queue = deque([user_id])
    while queue:
        current = queue.popleft()
        for child in children_map.get(current, set()):
            if child not in visible:
                visible.add(child)
                queue.append(child)

    # --- 2. Upward visibility (ancestors up to N levels) ---
    if upward_levels != 0:
        current = user_id
        levels_walked = 0
        while True:
            parent = user_parent.get(current)
            if parent is None or parent in visible:
                break
            visible.add(parent)
            # Also add all subordinates of this ancestor
            anc_queue = deque([parent])
            while anc_queue:
                node = anc_queue.popleft()
                for child in children_map.get(node, set()):
                    if child not in visible:
                        visible.add(child)
                        anc_queue.append(child)
            levels_walked += 1
            if upward_levels > 0 and levels_walked >= upward_levels:
                break
            current = parent

    # --- 3. Peer access (siblings under same parent + their subordinates) ---
    if peer_access:
        my_parent = user_parent.get(user_id)
        if my_parent is not None:
            siblings = children_map.get(my_parent, set())
            sub_queue = deque(s for s in siblings if s not in visible)
            while sub_queue:
                current = sub_queue.popleft()
                if current not in visible:
                    visible.add(current)
                for child in children_map.get(current, set()):
                    if child not in visible:
                        visible.add(child)
                        sub_queue.append(child)

    return visible
