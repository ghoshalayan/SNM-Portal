from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class QuotationFormat(Base, AuditMixin):
    __tablename__ = "QuotationFormat"

    qfId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    formatName = Column(String(200), nullable=False)
    qHeader = Column(String, nullable=True)
    qContent = Column(String, nullable=True)
    qFooter = Column(String, nullable=True)
    isCurrent = Column(Boolean, default=False, nullable=False)

    company = relationship("Company", foreign_keys=[companyId])
