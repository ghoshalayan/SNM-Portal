from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class ContactType(Base, AuditMixin):
    __tablename__ = "ContactType"

    contactTypeId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    contactType = Column(String(100), nullable=False)
