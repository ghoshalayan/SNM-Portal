from sqlalchemy import Column, Integer, String, Text, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class TermsNConditionMaster(Base, AuditMixin):
    __tablename__ = "TermsNConditionMaster"

    tncId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    tncName = Column(String(200), nullable=False)
    tncDescription = Column(Text, nullable=True)
