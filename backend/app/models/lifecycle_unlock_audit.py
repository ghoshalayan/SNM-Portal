from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import AuditMixin


class LifecycleUnlockAudit(Base, AuditMixin):
    """One row per ``Unlock & Edit`` action across any of the four
    lifecycle stages. The privileged escape valve writes a row here so
    admins can trace who unlocked which entity, when, and why.

    The action does NOT change the unlocked entity's status — it just
    permits in-place edits while the row is non-Draft. The audit row
    itself is the only persistent trace.
    """
    __tablename__ = "LifecycleUnlockAudit"

    auditId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    # Discriminator: 'Quotation' | 'PurchaseOrder' | 'Viability' | 'Annexure'
    stage = Column(String(20), nullable=False)
    # Polymorphic FK by intent — points at the relevant table's PK
    # (quotId / quotPOId / viabilityId / annexureId). Not a hard FK
    # because SQL Server can't model polymorphic foreign keys cleanly;
    # the service layer enforces stage→table consistency on insert.
    entityId = Column(Integer, nullable=False)

    unlockedBy = Column(Integer, ForeignKey("UserMaster.userId"), nullable=False)
    unlockedOn = Column(DateTime, nullable=False)
    reason = Column(String(500), nullable=True)

    unlocked_by_user = relationship("User", foreign_keys=[unlockedBy])
