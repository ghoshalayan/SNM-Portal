from sqlalchemy import Column, Integer, String, Numeric, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class CustomerEnquiry(Base, AuditMixin):
    __tablename__ = "CustomerEnquiry"

    enqid = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    ownerUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    ownerRoleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=True)
    customerId = Column(Integer, ForeignKey("CustomerMaster.customerId"), nullable=False)
    customerContactId = Column(Integer, ForeignKey("CustomerContacts.customerContactId"), nullable=True)
    siteId = Column(Integer, ForeignKey("CustomerSite.siteId"), nullable=True)
    enqNo = Column(String(50), nullable=True)
    enqDate = Column(Date, nullable=True)
    enqMode = Column(String(50), nullable=True)
    description = Column(String(500), nullable=True)
    validityDays = Column(Integer, nullable=True)
    status = Column(String(50), default="New", nullable=True)

    owner = relationship("User", foreign_keys=[ownerUserId])
    owner_role = relationship("Role", foreign_keys=[ownerRoleId])
    customer = relationship("CustomerMaster", foreign_keys=[customerId])
    contact = relationship("CustomerContacts", foreign_keys=[customerContactId])
    site = relationship("CustomerSite", foreign_keys=[siteId])
    details = relationship("CustomerEnquiryDetails", back_populates="enquiry")


class CustomerEnquiryDetails(Base, AuditMixin):
    __tablename__ = "CustomerEnquiryDetails"

    enqdtlid = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    enqid = Column(Integer, ForeignKey("CustomerEnquiry.enqid"), nullable=False)
    itemid = Column(Integer, ForeignKey("ItemName.itemId"), nullable=True)
    itemGradeName = Column(String(100), nullable=True)
    itemDia = Column(String(50), nullable=True)
    itemLength = Column(String(50), nullable=True)
    itemUnit = Column(String(20), nullable=True)
    quantity = Column(Numeric(18, 2), nullable=True)
    remarks = Column(String(500), nullable=True)

    enquiry = relationship("CustomerEnquiry", back_populates="details")
    item = relationship("ItemName", foreign_keys=[itemid])


class CustomerEnquiryCosting(Base, AuditMixin):
    __tablename__ = "CustomerEnquiryCosting"

    enqCostingId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    enqid = Column(Integer, ForeignKey("CustomerEnquiry.enqid"), nullable=False)
    enqdtlid = Column(Integer, ForeignKey("CustomerEnquiryDetails.enqdtlid"), nullable=False)
    versionNo = Column(Integer, default=1, nullable=False)

    # Cost heads
    TPWGST = Column(Numeric(18, 2), nullable=True)
    Marketing = Column(Numeric(18, 2), nullable=True)
    FreightTrailer = Column(Numeric(18, 2), nullable=True)
    FreightTruck = Column(Numeric(18, 2), nullable=True)
    Unloading = Column(Numeric(18, 2), nullable=True)
    OHD = Column(Numeric(18, 2), nullable=True)
    IFC = Column(Numeric(18, 2), nullable=True)
    WeighmentDiff = Column(Numeric(18, 2), nullable=True)
    CD = Column(Numeric(18, 2), nullable=True)
    SWECharge = Column(Numeric(18, 2), nullable=True)
    CRS = Column(Numeric(18, 2), nullable=True)
    IncCharge = Column(Numeric(18, 2), nullable=True)
    ShortLnthCharge = Column(Numeric(18, 2), nullable=True)
    SpeciFicLnthCharge = Column(Numeric(18, 2), nullable=True)
    ExtraCharge = Column(Numeric(18, 2), nullable=True)
    Fluctuation = Column(Numeric(18, 2), nullable=True)
    Commission = Column(Numeric(18, 2), nullable=True)
    Misc = Column(Numeric(18, 2), nullable=True)
    Testing = Column(Numeric(18, 2), nullable=True)
    MOUTOD = Column(Numeric(18, 2), nullable=True)
    SplDisc = Column(Numeric(18, 2), nullable=True)
    JC = Column(Numeric(18, 2), nullable=True)
    basicRate = Column(Numeric(18, 2), nullable=True)
    GST = Column(Numeric(18, 2), nullable=True)
    EXFORPrice = Column(Numeric(18, 2), nullable=True)

    enquiry = relationship("CustomerEnquiry", foreign_keys=[enqid])
    detail = relationship("CustomerEnquiryDetails", foreign_keys=[enqdtlid])


class CustomerEnqFollowUp(Base, AuditMixin):
    __tablename__ = "CustomerEnqFollowUp"

    engfollowupid = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    enqid = Column(Integer, ForeignKey("CustomerEnquiry.enqid"), nullable=False)
    followupdate = Column(Date, nullable=True)
    followupremarks = Column(String(500), nullable=True)
    followupmode = Column(String(50), nullable=True)
    nextfollowupdate = Column(Date, nullable=True)

    enquiry = relationship("CustomerEnquiry", foreign_keys=[enqid])
