"""KRO-style location subset enforcement and cascade logic.

Triggered by Role.enforceChildLocationSubset flag:
- On location assignment: validate user's locations ⊆ their reportTo's locations
- On reassignment (new reportTo): REPLACE user's locations with new reportTo's full set
- On reportTo's location reduction: CASCADE-NARROW child locations to intersection

Used via the unified AccessContext pipeline — nothing here depends on role names,
purely on the enforceChildLocationSubset flag on the target user's role.
"""

from typing import Optional, Set, Tuple, List
from sqlalchemy.orm import Session

from app.models.user import UserRoleMap
from app.models.role import Role
from app.models.user_location_map import UserLocationMap


def _get_role_of_user(db: Session, user_id: int, company_id: int) -> Optional[Role]:
    """Return the active role of a user in a company."""
    row = (
        db.query(Role)
        .join(UserRoleMap, UserRoleMap.roleId == Role.roleId)
        .filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
        )
        .first()
    )
    return row


def _get_report_to(db: Session, user_id: int, company_id: int) -> Optional[int]:
    row = (
        db.query(UserRoleMap.reportTo)
        .filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
        )
        .first()
    )
    return row[0] if row and row[0] else None


def _get_user_location_tuples(db: Session, user_id: int, company_id: int) -> List[Tuple[int, int, Optional[int]]]:
    """Return (countryid, stateid, districtid) tuples for a user's active location mappings."""
    rows = (
        db.query(
            UserLocationMap.countryid,
            UserLocationMap.stateid,
            UserLocationMap.districtid,
        )
        .filter(
            UserLocationMap.userId == user_id,
            UserLocationMap.companyId == company_id,
            UserLocationMap.isActive == True,
        )
        .all()
    )
    return [(r.countryid, r.stateid, r.districtid) for r in rows]


def _build_allowed_set(tuples: List[Tuple[int, int, Optional[int]]]) -> Tuple[Set[int], Set[Tuple[int, int]]]:
    """Split tuples into (full_state_ids, specific_state_district_pairs).
    A stateid with NULL districtid = full state access (all districts).
    """
    full_states: Set[int] = set()
    specific: Set[Tuple[int, int]] = set()
    for _, sid, did in tuples:
        if did is None:
            full_states.add(sid)
        else:
            specific.add((sid, did))
    return full_states, specific


def _location_in_allowed(tup: Tuple[int, int, Optional[int]], full_states: Set[int], specific: Set[Tuple[int, int]]) -> bool:
    _, sid, did = tup
    if sid in full_states:
        return True
    if did is None:
        # Trying to assign full-state — only allowed if parent also has full state
        return False
    return (sid, did) in specific


def validate_subset_against_parent(
    db: Session,
    user_id: int,
    company_id: int,
    new_mappings: List[Tuple[int, int, Optional[int]]],
) -> None:
    """If the user's role has enforceChildLocationSubset, validate that
    new_mappings ⊆ the user's reportTo's allotted locations.
    Raises ValueError with a human-friendly message on failure.
    """
    role = _get_role_of_user(db, user_id, company_id)
    if not role or not getattr(role, "enforceChildLocationSubset", False):
        return  # no enforcement

    parent_id = _get_report_to(db, user_id, company_id)
    if not parent_id:
        # No parent → nothing to enforce against. Allow.
        return

    parent_tuples = _get_user_location_tuples(db, parent_id, company_id)
    full_states, specific = _build_allowed_set(parent_tuples)

    for tup in new_mappings:
        if not _location_in_allowed(tup, full_states, specific):
            raise ValueError(
                f"Location (state={tup[1]}, district={tup[2]}) is outside your "
                f"reporting manager's allotted locations."
            )


def inherit_from_parent(
    db: Session,
    user_id: int,
    company_id: int,
    actor_user_id: int,
) -> int:
    """Replace user's location mappings with the parent's full set.
    Use on KRO creation/reassignment.

    Triggers when role has BOTH:
      - locationScopeRequired = True (user is location-scoped)
      - enforceChildLocationSubset = True (user must inherit from parent)

    Returns number of mappings inherited (0 = no-op).
    """
    role = _get_role_of_user(db, user_id, company_id)
    if not role:
        return 0

    # Check the flag — must be explicitly True
    enforce = getattr(role, "enforceChildLocationSubset", False)
    loc_required = getattr(role, "locationScopeRequired", True)
    if not enforce or not loc_required:
        return 0

    parent_id = _get_report_to(db, user_id, company_id)
    if not parent_id:
        return 0

    parent_tuples = _get_user_location_tuples(db, parent_id, company_id)
    if not parent_tuples:
        # Parent has no locations either — nothing to inherit
        return 0

    # Deactivate current mappings
    db.query(UserLocationMap).filter(
        UserLocationMap.userId == user_id,
        UserLocationMap.companyId == company_id,
    ).update({"isActive": False})

    # Copy parent's full location set
    count = 0
    for cid, sid, did in parent_tuples:
        # Upsert: reactivate if exists, else create
        existing = db.query(UserLocationMap).filter(
            UserLocationMap.userId == user_id,
            UserLocationMap.companyId == company_id,
            UserLocationMap.countryid == cid,
            UserLocationMap.stateid == sid,
            UserLocationMap.districtid == did if did is not None
            else UserLocationMap.districtid.is_(None),
        ).first()
        if existing:
            existing.isActive = True
            existing.lastupdateby = actor_user_id
        else:
            db.add(UserLocationMap(
                userId=user_id,
                companyId=company_id,
                countryid=cid,
                stateid=sid,
                districtid=did,
                createdby=actor_user_id,
            ))
        count += 1
    db.commit()
    return count


def cascade_narrow_children(
    db: Session,
    parent_user_id: int,
    company_id: int,
    actor_user_id: int,
) -> int:
    """When a parent's locations are reduced, narrow every child's locations
    (whose role has enforceChildLocationSubset) to the intersection with parent.
    Returns total number of child mapping rows deactivated.
    """
    # Find all direct children in company
    children = (
        db.query(UserRoleMap.userId)
        .filter(
            UserRoleMap.reportTo == parent_user_id,
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
        )
        .all()
    )
    child_ids = [c.userId for c in children]
    if not child_ids:
        return 0

    parent_tuples = _get_user_location_tuples(db, parent_user_id, company_id)
    full_states, specific = _build_allowed_set(parent_tuples)

    deactivated = 0
    for child_id in child_ids:
        child_role = _get_role_of_user(db, child_id, company_id)
        if not child_role or not getattr(child_role, "enforceChildLocationSubset", False):
            continue

        child_rows = (
            db.query(UserLocationMap)
            .filter(
                UserLocationMap.userId == child_id,
                UserLocationMap.companyId == company_id,
                UserLocationMap.isActive == True,
            )
            .all()
        )
        for row in child_rows:
            tup = (row.countryid, row.stateid, row.districtid)
            if not _location_in_allowed(tup, full_states, specific):
                row.isActive = False
                row.lastupdateby = actor_user_id
                deactivated += 1

        # Recurse — child's children may also need narrowing
        deactivated += cascade_narrow_children(db, child_id, company_id, actor_user_id)

    db.commit()
    return deactivated
