from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class DeliveryTerm(Base, AuditMixin):
    __tablename__ = "DeliveryTerm"

    deliveryTermId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    deliveryTerm = Column(String(200), nullable=False)


class DeliveryMode(Base, AuditMixin):
    __tablename__ = "DeliveryMode"

    deliveryModeId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    deliveryMode = Column(String(200), nullable=False)
