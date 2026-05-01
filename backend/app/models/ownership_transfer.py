from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class OwnershipTransfer(Base, AuditMixin):
    __tablename__ = "OwnershipTransfer"

    transferId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    entityType = Column(String(20), nullable=False)  # "enquiry" or "quotation"
    entityId = Column(Integer, nullable=False)        # enqid or quotId
    fromUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=False)
    toUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=False)
    requestedBy = Column(Integer, ForeignKey("UserMaster.userId"), nullable=False)
    requestedOn = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    approvedBy = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    approvedOn = Column(DateTime, nullable=True)
    remarks = Column(String(500), nullable=True)

    from_user = relationship("User", foreign_keys=[fromUserId])
    to_user = relationship("User", foreign_keys=[toUserId])
    requested_by_user = relationship("User", foreign_keys=[requestedBy])
    approved_by_user = relationship("User", foreign_keys=[approvedBy])
