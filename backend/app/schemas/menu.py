from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class MenuCreate(BaseModel):
    menuName: str
    menuUrl: Optional[str] = None
    menuIcon: Optional[str] = None
    parentMenuId: Optional[int] = None
    menuOrder: int = 0


class MenuUpdate(BaseModel):
    menuName: Optional[str] = None
    menuUrl: Optional[str] = None
    menuIcon: Optional[str] = None
    parentMenuId: Optional[int] = None
    menuOrder: Optional[int] = None


class MenuResponse(BaseModel):
    menuId: int
    companyId: int
    menuName: str
    menuUrl: Optional[str] = None
    menuIcon: Optional[str] = None
    parentMenuId: Optional[int] = None
    menuOrder: int
    isActive: bool

    class Config:
        from_attributes = True


class MenuTreeNode(BaseModel):
    menuId: int
    menuName: str
    menuUrl: Optional[str] = None
    menuIcon: Optional[str] = None
    menuOrder: int
    children: List["MenuTreeNode"] = []


class RoleMenuPermission(BaseModel):
    menuId: int
    canAdd: bool = False
    canRead: bool = False
    canEdit: bool = False
    canDelete: bool = False
    canEditNumber: bool = False
    canApprove: bool = False
    canRevise: bool = False
    canTransferOwnership: bool = False
    canGenerateUnderOthers: bool = False


class RoleMenuPermissionResponse(BaseModel):
    menuId: int
    menuName: str
    canAdd: bool
    canRead: bool
    canEdit: bool
    canDelete: bool
    canEditNumber: bool
    canApprove: bool = False
    canRevise: bool = False
    canTransferOwnership: bool = False
    canGenerateUnderOthers: bool = False

    class Config:
        from_attributes = True
