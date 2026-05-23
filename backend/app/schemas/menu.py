from pydantic import BaseModel, ConfigDict
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
    # Reject unknown flag names. The save handler relies on
    # ``model_dump(exclude_unset=True)`` to detect which flags the caller
    # actually sent; a typo like ``canConvret: true`` must NOT silently
    # be dropped by Pydantic's "ignore-extras" default — it would look
    # like the flag was simply omitted, leaving the real ``canConvert``
    # untouched, which is the same silent-failure shape we just fixed.
    # Forbid raises 422 instead, making the bug loud at the API edge.
    model_config = ConfigDict(extra="forbid")

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
    canApproveAnnexure: bool = False
    # Phase 1 lifecycle flags. Only meaningful on the Quotations menu.
    canConvert: bool = False
    canReactivate: bool = False
    canSubmitPO: bool = False
    canRejectPO: bool = False
    canApproveViability: bool = False
    canUnlockEditQuotation: bool = False
    canUnlockEditPO: bool = False
    canUnlockEditViability: bool = False
    canUnlockEditAnnexure: bool = False
    # LOI / Cycle CR — Phase 1A flags.
    canCaptureLOI: bool = False
    canStartNewCycle: bool = False
    # Post-Convert lifecycle Approve + Regenerate flags.
    canApproveFWS: bool = False
    canRegenerateFWS: bool = False
    canRegenerateViability: bool = False
    canRegenerateAnnexure: bool = False


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
    canApproveAnnexure: bool = False
    # Phase 1 lifecycle flags. Only meaningful on the Quotations menu.
    canConvert: bool = False
    canReactivate: bool = False
    canSubmitPO: bool = False
    canRejectPO: bool = False
    canApproveViability: bool = False
    canUnlockEditQuotation: bool = False
    canUnlockEditPO: bool = False
    canUnlockEditViability: bool = False
    canUnlockEditAnnexure: bool = False
    # LOI / Cycle CR — Phase 1A flags.
    canCaptureLOI: bool = False
    canStartNewCycle: bool = False
    # Post-Convert lifecycle Approve + Regenerate flags.
    canApproveFWS: bool = False
    canRegenerateFWS: bool = False
    canRegenerateViability: bool = False
    canRegenerateAnnexure: bool = False

    class Config:
        from_attributes = True
