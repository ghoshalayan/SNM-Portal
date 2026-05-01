from sqlalchemy import Column, Integer, String, Boolean, Numeric, DateTime, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class RawMaterialCost(Base, AuditMixin):
    __tablename__ = "RawMaterialCost"

    rawMaterialCostId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    dia = Column(String(50), nullable=False)
    tpcost = Column(Numeric(18, 2), nullable=False)
    effectedFrom = Column(DateTime, nullable=True)
    # Base price logic: one dia per company can be the base
    isBasePrice = Column(Boolean, default=False, nullable=False)
    diffFromBase = Column(Numeric(18, 2), nullable=True)  # NULL for base row, value for derived rows
