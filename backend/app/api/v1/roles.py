from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from pydantic import BaseModel as PydanticBaseModel
from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.models.role import Role
from app.models.user import UserRoleMap
from app.models.role_menu_map import RoleMenuMap
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse


class RoleSettingsUpdate(PydanticBaseModel):
    numGenMode: str
    peerAccess: Optional[bool] = None
    peerSubtree: Optional[bool] = None
    roleLevel: Optional[int] = None
    locationScopeRequired: Optional[bool] = None
    canApproveTransfers: Optional[bool] = None
    upwardVisibilityLevels: Optional[int] = None
    # RBAC v2 new flags
    IsCompanyAdmin: Optional[bool] = None
    downwardLevels: Optional[int] = None
    upwardLevels: Optional[int] = None
    includeSubtreeOnUpward: Optional[bool] = None
    enforceChildLocationSubset: Optional[bool] = None

router = APIRouter()


@router.get("", response_model=List[RoleResponse])
def get_roles(
    companyId: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    # Super admins can query roles for any company; others are locked to their own
    target_company = current_user.company_id
    if companyId is not None:
        if current_user.is_super_admin:
            target_company = companyId
        # Non-super-admins: ignore the param, always use their own company

    return db.query(Role).filter(
        Role.companyId == target_company,
        Role.isActive == True,
    ).all()


@router.get("/{role_id}", response_model=RoleResponse)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    role = db.query(Role).filter(
        Role.roleId == role_id,
        Role.companyId == current_user.company_id,
        Role.isActive == True,
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    role = Role(
        **data.model_dump(),
        companyId=current_user.company_id,
        createdby=current_user.user_id,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    role = db.query(Role).filter(
        Role.roleId == role_id,
        Role.companyId == current_user.company_id,
        Role.isActive == True,
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(role, key, value)
    role.lastupdateby = current_user.user_id
    db.commit()
    db.refresh(role)
    return role


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    role = db.query(Role).filter(
        Role.roleId == role_id,
        Role.companyId == current_user.company_id,
        Role.isActive == True,
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    role.isActive = False
    role.lastupdateby = current_user.user_id

    # Cascade: deactivate related UserRoleMap and RoleMenuMap entries
    db.query(UserRoleMap).filter(UserRoleMap.roleId == role_id, UserRoleMap.isActive == True).update(
        {"isActive": False, "lastupdateby": current_user.user_id}
    )
    db.query(RoleMenuMap).filter(RoleMenuMap.roleId == role_id, RoleMenuMap.isActive == True).update(
        {"isActive": False, "lastupdateby": current_user.user_id}
    )

    db.commit()


# ===== Number Generation Mode =====

@router.get("/{role_id}/num-gen-mode")
def get_num_gen_mode(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    role = db.query(Role).filter(
        Role.roleId == role_id,
        Role.companyId == current_user.company_id,
        Role.isActive == True,
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return {
        "numGenMode": role.numGenMode,
        "peerAccess": role.peerAccess,
        "peerSubtree": getattr(role, "peerSubtree", False),
        "roleLevel": role.roleLevel,
        "locationScopeRequired": role.locationScopeRequired,
        "canApproveTransfers": role.canApproveTransfers,
        "upwardVisibilityLevels": role.upwardVisibilityLevels,
        "IsCompanyAdmin": getattr(role, "IsCompanyAdmin", False),
        "downwardLevels": getattr(role, "downwardLevels", -1),
        "upwardLevels": getattr(role, "upwardLevels", role.upwardVisibilityLevels),
        "includeSubtreeOnUpward": getattr(role, "includeSubtreeOnUpward", True),
        "enforceChildLocationSubset": getattr(role, "enforceChildLocationSubset", False),
    }


@router.put("/{role_id}/num-gen-mode")
def update_role_settings(
    role_id: int,
    data: RoleSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if data.numGenMode not in ("own_code", "parent_code", "select_code"):
        raise HTTPException(status_code=400, detail="Invalid numGenMode")
    role = db.query(Role).filter(
        Role.roleId == role_id,
        Role.companyId == current_user.company_id,
        Role.isActive == True,
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    role.numGenMode = data.numGenMode
    if data.peerAccess is not None:
        role.peerAccess = data.peerAccess
    if data.peerSubtree is not None and hasattr(role, "peerSubtree"):
        role.peerSubtree = data.peerSubtree
    if data.roleLevel is not None:
        role.roleLevel = data.roleLevel
    if data.locationScopeRequired is not None:
        role.locationScopeRequired = data.locationScopeRequired
    if data.canApproveTransfers is not None:
        role.canApproveTransfers = data.canApproveTransfers
    if data.upwardVisibilityLevels is not None:
        role.upwardVisibilityLevels = data.upwardVisibilityLevels
    # RBAC v2 new flags
    if data.IsCompanyAdmin is not None and hasattr(role, "IsCompanyAdmin"):
        role.IsCompanyAdmin = data.IsCompanyAdmin
    if data.downwardLevels is not None and hasattr(role, "downwardLevels"):
        role.downwardLevels = data.downwardLevels
    if data.upwardLevels is not None and hasattr(role, "upwardLevels"):
        role.upwardLevels = data.upwardLevels
    if data.includeSubtreeOnUpward is not None and hasattr(role, "includeSubtreeOnUpward"):
        role.includeSubtreeOnUpward = data.includeSubtreeOnUpward
    if data.enforceChildLocationSubset is not None and hasattr(role, "enforceChildLocationSubset"):
        role.enforceChildLocationSubset = data.enforceChildLocationSubset
    role.lastupdateby = current_user.user_id
    db.commit()

    # Role flags affect visibility BFS + location bypass — invalidate caches
    from app.services.cache_invalidation import on_role_change
    on_role_change(role_id)

    return {
        "numGenMode": role.numGenMode,
        "peerAccess": role.peerAccess,
        "roleLevel": role.roleLevel,
        "locationScopeRequired": role.locationScopeRequired,
        "canApproveTransfers": role.canApproveTransfers,
        "upwardVisibilityLevels": role.upwardVisibilityLevels,
    }
