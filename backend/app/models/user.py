from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class User(Base, AuditMixin):
    __tablename__ = "UserMaster"

    userId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    userName = Column(String(100), nullable=False)
    userCode = Column(String(50), nullable=True)
    userEmail = Column(String(100), nullable=True)
    userPhone = Column(String(20), nullable=True)
    userLogin = Column(String(50), nullable=False, unique=True)
    userPassword = Column(String(255), nullable=False)  # bcrypt hash
    userDesignation = Column(String(100), nullable=True)
    reportTo = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)

    company = relationship("Company", foreign_keys=[companyId])
    report_to_user = relationship("User", remote_side=[userId], foreign_keys=[reportTo])
    role_mappings = relationship("UserRoleMap", back_populates="user", foreign_keys="[UserRoleMap.userId]")


class UserRoleMap(Base, AuditMixin):
    __tablename__ = "UserRoleMap"

    userRoleMapId = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=False)
    roleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=False)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    isDefault = Column(Boolean, default=False, nullable=False)
    reportTo = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)

    user = relationship("User", back_populates="role_mappings", foreign_keys=[userId])
    role = relationship("Role", foreign_keys=[roleId])
    company = relationship("Company", foreign_keys=[companyId])
    report_to_user = relationship("User", foreign_keys=[reportTo])
