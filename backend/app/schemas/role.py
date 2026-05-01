from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RoleCreate(BaseModel):
    roleName: str
    IsSuperAdmin: bool = False
    numGenMode: str = "select_code"
    peerAccess: bool = False
    roleLevel: int = 0
    locationScopeRequired: bool = True
    canApproveTransfers: bool = False
    upwardVisibilityLevels: int = 0


class RoleUpdate(BaseModel):
    roleName: Optional[str] = None
    IsSuperAdmin: Optional[bool] = None
    numGenMode: Optional[str] = None
    peerAccess: Optional[bool] = None
    roleLevel: Optional[int] = None
    locationScopeRequired: Optional[bool] = None
    canApproveTransfers: Optional[bool] = None
    upwardVisibilityLevels: Optional[int] = None


class RoleResponse(BaseModel):
    roleId: int
    companyId: int
    roleName: str
    IsSuperAdmin: bool
    numGenMode: str
    peerAccess: bool
    roleLevel: int
    locationScopeRequired: bool
    canApproveTransfers: bool
    upwardVisibilityLevels: int
    isActive: bool
    createdon: Optional[datetime] = None

    class Config:
        from_attributes = True
