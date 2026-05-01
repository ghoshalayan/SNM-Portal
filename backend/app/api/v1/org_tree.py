"""Organization Tree API — visualize and manage the reporting hierarchy.

Key design decisions:
- reportTo is stored per-company in UserRoleMap (a user can have different
  managers in different companies).
- SuperAdmin users are always visible in every company's org tree.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.models.user import User, UserRoleMap
from app.models.role import Role

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class OrgNodeResponse(BaseModel):
    userId: int
    userName: str
    userCode: Optional[str] = None
    userEmail: Optional[str] = None
    reportTo: Optional[int] = None
    roleName: Optional[str] = None
    isSuperAdmin: bool = False

    class Config:
        from_attributes = True


class AssignRequest(BaseModel):
    userId: int
    reportTo: Optional[int] = None  # None → unassign (remove from tree)


class BulkAssignRequest(BaseModel):
    assignments: List[AssignRequest]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=List[OrgNodeResponse])
def get_org_tree(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return all active users visible to this company with company-specific
    reportTo and role info.

    Visible users:
    - Users with a UserRoleMap entry for this company
    - Users whose primary companyId matches this company
    - ALL SuperAdmin users (visible in every company)

    reportTo is read from UserRoleMap.reportTo (company-specific).
    """
    company_id = current_user.company_id

    # IDs of users mapped to this company
    mapped_user_ids = (
        db.query(UserRoleMap.userId)
        .filter(
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
        )
        .subquery()
    )

    # IDs of SuperAdmin users (any user who has at least one super-admin role)
    super_admin_user_ids = (
        db.query(UserRoleMap.userId)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(
            UserRoleMap.isActive == True,
            Role.IsSuperAdmin == True,
        )
        .subquery()
    )

    users = (
        db.query(User)
        .filter(
            User.isActive == True,
            or_(
                User.companyId == company_id,
                User.userId.in_(mapped_user_ids),
                User.userId.in_(super_admin_user_ids),
            ),
        )
        .all()
    )

    result: list[OrgNodeResponse] = []
    for u in users:
        # Get the UserRoleMap for this company (for reportTo + role)
        urm = (
            db.query(UserRoleMap)
            .filter(
                UserRoleMap.userId == u.userId,
                UserRoleMap.companyId == company_id,
                UserRoleMap.isActive == True,
            )
            .first()
        )

        role_name = None
        report_to = None
        is_super_admin = False

        if urm:
            report_to = urm.reportTo
            role = db.query(Role).filter(Role.roleId == urm.roleId).first()
            if role:
                role_name = role.roleName
                is_super_admin = role.IsSuperAdmin
        else:
            # SuperAdmin without a mapping for this company — check their role
            sa_urm = (
                db.query(UserRoleMap)
                .join(Role, UserRoleMap.roleId == Role.roleId)
                .filter(
                    UserRoleMap.userId == u.userId,
                    UserRoleMap.isActive == True,
                    Role.IsSuperAdmin == True,
                )
                .first()
            )
            if sa_urm:
                role = db.query(Role).filter(Role.roleId == sa_urm.roleId).first()
                role_name = role.roleName if role else "Super Admin"
                is_super_admin = True

        result.append(OrgNodeResponse(
            userId=u.userId,
            userName=u.userName,
            userCode=u.userCode,
            userEmail=u.userEmail,
            reportTo=report_to,
            roleName=role_name,
            isSuperAdmin=is_super_admin,
        ))

    return result


@router.put("/assign")
def assign_report_to(
    data: AssignRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Assign or update a user's reportTo within this company.

    - reportTo = null   → remove from tree (unassign)
    - reportTo = userId  → make root node (self-reference convention)
    - reportTo = otherId → place under that user

    Updates UserRoleMap.reportTo (company-specific). If the user has no
    mapping for this company yet (e.g. a SuperAdmin), one is created.
    """
    company_id = current_user.company_id

    user = _get_visible_user(db, data.userId, company_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate target
    if data.reportTo is not None and data.reportTo != data.userId:
        target = _get_visible_user(db, data.reportTo, company_id)
        if not target:
            raise HTTPException(status_code=404, detail="Target user not found")

        if _creates_cycle(db, data.userId, data.reportTo, company_id):
            raise HTTPException(
                status_code=400,
                detail="This assignment would create a circular reporting chain",
            )

    # Update or create UserRoleMap entry for this company
    _set_report_to(db, data.userId, company_id, data.reportTo, current_user.user_id)
    db.commit()

    # Invalidate visibility cache company-wide (reportTo change affects BFS)
    from app.services.cache_invalidation import on_user_role_change, on_user_location_change
    on_user_role_change(data.userId, company_id)

    # RBAC v2: auto-inherit locations from new parent if user's role enforces child-subset
    inherited = 0
    if data.reportTo and data.reportTo != data.userId:
        from app.services.kro_location_service import inherit_from_parent
        inherited = inherit_from_parent(db, data.userId, company_id, current_user.user_id)
        if inherited:
            on_user_location_change(data.userId, company_id)

    return {"message": "Assignment updated", "locationsInherited": inherited}


@router.put("/bulk-assign")
def bulk_assign(
    data: BulkAssignRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Batch update multiple reportTo assignments at once."""
    company_id = current_user.company_id

    # Validate all assignments before applying any
    for item in data.assignments:
        user = _get_visible_user(db, item.userId, company_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User {item.userId} not found or not visible in this company",
            )

        if item.reportTo is not None and item.reportTo != item.userId:
            target = _get_visible_user(db, item.reportTo, company_id)
            if not target:
                raise HTTPException(
                    status_code=404,
                    detail=f"Target user {item.reportTo} not found or not visible in this company",
                )
            if _creates_cycle(db, item.userId, item.reportTo, company_id):
                raise HTTPException(
                    status_code=400,
                    detail=f"Assignment of user {item.userId} to {item.reportTo} creates a cycle",
                )

    # Apply all assignments
    for item in data.assignments:
        _set_report_to(db, item.userId, company_id, item.reportTo, current_user.user_id)

    db.commit()

    # Invalidate visibility cache once for the whole company (cheaper than per-item)
    from app.services.cache_invalidation import on_user_role_change, on_user_location_change
    if data.assignments:
        on_user_role_change(data.assignments[0].userId, company_id)

    # RBAC v2: auto-inherit locations for each reassigned user
    from app.services.kro_location_service import inherit_from_parent
    total_inherited = 0
    for item in data.assignments:
        if item.reportTo and item.reportTo != item.userId:
            total_inherited += inherit_from_parent(
                db, item.userId, company_id, current_user.user_id,
            )
    if total_inherited:
        on_user_location_change(0, company_id)  # company-wide invalidation

    return {"message": "Bulk assignment complete", "locationsInherited": total_inherited}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_visible_user(db: Session, user_id: int, company_id: int):
    """Find a user by ID if they are visible in the given company.

    Visible = primary companyId matches OR has UserRoleMap OR is SuperAdmin.
    """
    mapped_user_ids = (
        db.query(UserRoleMap.userId)
        .filter(
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
        )
        .subquery()
    )
    super_admin_user_ids = (
        db.query(UserRoleMap.userId)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(
            UserRoleMap.isActive == True,
            Role.IsSuperAdmin == True,
        )
        .subquery()
    )
    return db.query(User).filter(
        User.userId == user_id,
        User.isActive == True,
        or_(
            User.companyId == company_id,
            User.userId.in_(mapped_user_ids),
            User.userId.in_(super_admin_user_ids),
        ),
    ).first()


def _set_report_to(
    db: Session, user_id: int, company_id: int,
    report_to, updated_by: int,
) -> None:
    """Set reportTo on UserRoleMap for this user+company. Creates mapping if
    none exists (needed for SuperAdmins who may not have a mapping yet)."""
    urm = (
        db.query(UserRoleMap)
        .filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
        )
        .first()
    )

    # Sync to User.reportTo on UserMaster (for display in user list/dialog)
    user = db.query(User).filter(User.userId == user_id).first()
    if user:
        user.reportTo = report_to
        user.lastupdateby = updated_by

    if urm:
        urm.reportTo = report_to
        urm.lastupdateby = updated_by
    else:
        # SuperAdmin with no mapping for this company — find their SA role
        sa_urm = (
            db.query(UserRoleMap)
            .join(Role, UserRoleMap.roleId == Role.roleId)
            .filter(
                UserRoleMap.userId == user_id,
                UserRoleMap.isActive == True,
                Role.IsSuperAdmin == True,
            )
            .first()
        )
        if sa_urm:
            new_urm = UserRoleMap(
                userId=user_id,
                roleId=sa_urm.roleId,
                companyId=company_id,
                isDefault=False,
                reportTo=report_to,
                createdby=updated_by,
            )
            db.add(new_urm)


def _creates_cycle(
    db: Session, user_id: int, new_parent_id: int, company_id: int
) -> bool:
    """Walk up the company-specific chain from new_parent_id; if we hit
    user_id → cycle. Uses UserRoleMap.reportTo (not User.reportTo)."""
    if user_id == new_parent_id:
        return False  # self-reference = root, not a cycle

    visited = {user_id}
    current = new_parent_id

    while current is not None:
        if current in visited:
            return True
        visited.add(current)
        row = (
            db.query(UserRoleMap.reportTo)
            .filter(
                UserRoleMap.userId == current,
                UserRoleMap.companyId == company_id,
                UserRoleMap.isActive == True,
            )
            .first()
        )
        if not row:
            break
        parent = row[0]
        # Self-reference stops traversal (root node)
        if parent == current:
            break
        current = parent

    return False
