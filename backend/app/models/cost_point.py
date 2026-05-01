from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class CostPointMaster(Base, AuditMixin):
    __tablename__ = "CostPointMaster"

    costPointId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    costPointName = Column(String(100), nullable=False)
    isPrimary = Column(Boolean, default=False, nullable=False)
    isTax = Column(Boolean, default=False, nullable=False)
