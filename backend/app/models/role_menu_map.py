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
