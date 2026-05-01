from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class QuotActivityLog(Base):
    """Append-only audit trail for quotation lifecycle events.

    Not using AuditMixin on purpose — these rows are themselves the audit.
    Writes happen inline with each lifecycle endpoint; never updated or soft-deleted.
    """
    __tablename__ = "QuotActivityLog"

    logId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)
    action = Column(String(100), nullable=False)
    status = Column(String(50), nullable=True)   # quotation stage at/after action
    outcome = Column(String(20), nullable=False, default="Success")  # 'Success' | 'Failure'
    details = Column(Text, nullable=True)
    actionOn = Column(DateTime, nullable=False)
    actionByUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    actionByName = Column(String(200), nullable=True)

    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    action_by_user = relationship("User", foreign_keys=[actionByUserId])
