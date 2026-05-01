from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class FinancialYear(Base, AuditMixin):
    __tablename__ = "FinancialYear"

    fyId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    fyName = Column(String(100), nullable=False)
    fyCode = Column(String(50), nullable=False)
    isCurrent = Column(Boolean, default=False, nullable=False)
