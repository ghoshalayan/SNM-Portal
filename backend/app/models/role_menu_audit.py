from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class RoleMenuMapAudit(Base):
    """Per-flag change record for role-menu permissions.

    Write-only from the app's perspective — new rows accrete on every save,
    never updated or deleted. Feeds the audit history panel + compliance.
    """
    __tablename__ = "RoleMenuMapAudit"

    auditId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    roleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=False)
    menuId = Column(Integer, ForeignKey("MenuMaster.menuId"), nullable=False)
    field = Column(String(50), nullable=False)     # e.g. "CanEdit", "CanApprove"
    oldValue = Column(Boolean, nullable=True)
    newValue = Column(Boolean, nullable=True)
    changedby = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    changedon = Column(DateTime, nullable=False)

    role = relationship("Role", foreign_keys=[roleId])
    menu = relationship("MenuMaster", foreign_keys=[menuId])
    changed_by_user = relationship("User", foreign_keys=[changedby])
