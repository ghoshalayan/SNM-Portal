from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class MenuMaster(Base, AuditMixin):
    __tablename__ = "MenuMaster"

    menuId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    menuName = Column(String(100), nullable=False)
    menuUrl = Column(String(200), nullable=True)
    menuIcon = Column(String(100), nullable=True)
    parentMenuId = Column(Integer, ForeignKey("MenuMaster.menuId"), nullable=True)
    menuOrder = Column(Integer, default=0, nullable=False)

    parent = relationship("MenuMaster", remote_side=[menuId], backref="children")
