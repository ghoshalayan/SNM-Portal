from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class EnQStatusMaster(Base, AuditMixin):
    __tablename__ = "EnQStatusMaster"

    enqstatid = Column(Integer, primary_key=True, autoincrement=True)
    enqStatus = Column(String(50), nullable=False)
    stepno = Column(Integer, nullable=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)

    company = relationship("Company", foreign_keys=[companyId])


class QuotQStatusMaster(Base, AuditMixin):
    __tablename__ = "QuotQStatusMaster"

    quotstatid = Column(Integer, primary_key=True, autoincrement=True)
    quotStatus = Column(String(50), nullable=False)
    stepno = Column(Integer, nullable=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)

    company = relationship("Company", foreign_keys=[companyId])
