from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class CommunicationMode(Base, AuditMixin):
    __tablename__ = "CommunicationMode"

    commmodeId = Column(Integer, primary_key=True, autoincrement=True)
    commmode = Column(String(50), nullable=False)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)

    company = relationship("Company", foreign_keys=[companyId])


class CommunicationLog(Base, AuditMixin):
    __tablename__ = "CommunicationLog"

    commlogID = Column(BigInteger, primary_key=True, autoincrement=True)
    commmode = Column(String(50), nullable=True)
    contactto = Column(String(100), nullable=True)
    contactinfo = Column(String(500), nullable=True)
    enqid = Column(Integer, ForeignKey("CustomerEnquiry.enqid"), nullable=True)
    quoteid = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=True)
    commsubject = Column(String(500), nullable=True)
    commdescription = Column(String(5000), nullable=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    # RBAC v2: ownership tracking for hierarchy filtering
    ownerUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    ownerRoleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=True)

    company = relationship("Company", foreign_keys=[companyId])
    enquiry = relationship("CustomerEnquiry", foreign_keys=[enqid])
    quotation = relationship("QuotSummary", foreign_keys=[quoteid])
