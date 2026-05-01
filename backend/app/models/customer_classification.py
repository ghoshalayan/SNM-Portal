from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class CustomerClassification(Base, AuditMixin):
    __tablename__ = "CustomerClassification"

    classificationId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    classificationName = Column(String(100), nullable=False)
