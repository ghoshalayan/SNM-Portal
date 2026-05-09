from sqlalchemy import Column, Integer, Boolean, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class RoleMenuMap(Base, AuditMixin):
    __tablename__ = "RoleMenuMap"

    roleMenuMapId = Column(Integer, primary_key=True, autoincrement=True)
    roleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=False)
    menuId = Column(Integer, ForeignKey("MenuMaster.menuId"), nullable=False)
    CanAdd = Column(Boolean, default=False, nullable=False)
    CanRead = Column(Boolean, default=False, nullable=False)
    CanEdit = Column(Boolean, default=False, nullable=False)
    CanDelete = Column(Boolean, default=False, nullable=False)
    CanEditNumber = Column(Boolean, default=False, nullable=False)
    # Extended permissions (relevant to specific modules; unused on others)
    CanApprove = Column(Boolean, default=False, nullable=False)
    CanRevise = Column(Boolean, default=False, nullable=False)
    CanTransferOwnership = Column(Boolean, default=False, nullable=False)
    CanGenerateUnderOthers = Column(Boolean, default=False, nullable=False)
    # Granted only to the "Commercial HOD" role template — gates the
    # annexure /approve endpoint AND lets the holder edit an annexure
    # even after it has been approved (override of the regular lock).
    # Regular HODs keep CanApprove for quotation-level approval.
    CanApproveAnnexure = Column(Boolean, default=False, nullable=False)

    # ---- Phase 1 lifecycle flags ----
    # Forward gates and per-stage approvers. ``CanApprove`` continues
    # to gate quotation approval (legacy, unchanged). The flags below
    # are only meaningful on the "Quotations" menu — every lifecycle
    # endpoint already routes through that single menu.
    CanConvert = Column(Boolean, default=False, nullable=False)
    CanReactivate = Column(Boolean, default=False, nullable=False)
    CanSubmitPO = Column(Boolean, default=False, nullable=False)
    CanRejectPO = Column(Boolean, default=False, nullable=False)
    CanApproveViability = Column(Boolean, default=False, nullable=False)
    # Per-stage Unlock-and-Edit escape valves. Different roles can
    # hold different ones (e.g. only Commercial HOD ever unlocks an
    # approved annexure; only CompanyAdmin can unlock a converted
    # quotation). Flag granularity is per stage.
    CanUnlockEditQuotation = Column(Boolean, default=False, nullable=False)
    CanUnlockEditPO = Column(Boolean, default=False, nullable=False)
    CanUnlockEditViability = Column(Boolean, default=False, nullable=False)
    CanUnlockEditAnnexure = Column(Boolean, default=False, nullable=False)
