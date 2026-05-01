from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class QuotSummary(Base, AuditMixin):
    __tablename__ = "QuotSummary"

    quotId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    ownerUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    ownerRoleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=True)
    enqid = Column(Integer, ForeignKey("CustomerEnquiry.enqid"), nullable=True)
    customerId = Column(Integer, ForeignKey("CustomerMaster.customerId"), nullable=False)
    customerContactId = Column(Integer, ForeignKey("CustomerContacts.customerContactId"), nullable=True)
    siteId = Column(Integer, ForeignKey("CustomerSite.siteId"), nullable=True)
    quotNo = Column(String(50), nullable=True)
    quotDate = Column(Date, nullable=True)
    subject = Column(String(500), nullable=True)
    deliveryTermId = Column(Integer, ForeignKey("DeliveryTerm.deliveryTermId"), nullable=True)
    deliveryModeId = Column(Integer, ForeignKey("DeliveryMode.deliveryModeId"), nullable=True)
    refQuotNo = Column(String(50), nullable=True)
    remarks = Column(String(500), nullable=True)
    CustomerPONo = Column(String(50), nullable=True)
    CustomerPODate = Column(Date, nullable=True)
    revisionNo = Column(Integer, default=0, nullable=True)
    versionNo = Column(Integer, default=1, nullable=False)
    parentQuotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=True)
    approvedby = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    approvedon = Column(DateTime, nullable=True)
    status = Column(String(50), default="Draft", nullable=True)

    owner = relationship("User", foreign_keys=[ownerUserId])
    owner_role = relationship("Role", foreign_keys=[ownerRoleId])
    enquiry = relationship("CustomerEnquiry", foreign_keys=[enqid])
    customer = relationship("CustomerMaster", foreign_keys=[customerId])
    contact = relationship("CustomerContacts", foreign_keys=[customerContactId])
    site = relationship("CustomerSite", foreign_keys=[siteId])
    delivery_term = relationship("DeliveryTerm", foreign_keys=[deliveryTermId])
    delivery_mode = relationship("DeliveryMode", foreign_keys=[deliveryModeId])
    parent_quotation = relationship("QuotSummary", remote_side=[quotId], foreign_keys=[parentQuotId])
    approved_by_user = relationship("User", foreign_keys=[approvedby])
    details = relationship("QuotDetails", back_populates="quotation")
    terms = relationship("QuotTermsNConditions", back_populates="quotation")


class QuotDetails(Base, AuditMixin):
    __tablename__ = "QuotDetails"

    quotDtlId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)
    itemid = Column(Integer, ForeignKey("ItemName.itemId"), nullable=True)
    itemName = Column(String(200), nullable=True)
    itemGradeName = Column(String(100), nullable=True)
    itemDia = Column(String(50), nullable=True)
    itemLength = Column(String(50), nullable=True)
    itemUnit = Column(String(20), nullable=True)
    quantity = Column(Numeric(18, 2), nullable=True)

    # Cost heads (all per MT)
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

    modeOfDispatch = Column(String(200), nullable=True)

    # Calculated / GST
    basicRate = Column(Numeric(18, 2), nullable=True)
    totRate = Column(Numeric(18, 2), nullable=True)      # Total (Rs/MT) = SUM of cost heads
    gstMode = Column(String(20), default="IGST", nullable=True)  # 'IGST' or 'CGST_SGST'
    IGST = Column(Numeric(18, 2), nullable=True)
    CGST = Column(Numeric(18, 2), nullable=True)
    SGST = Column(Numeric(18, 2), nullable=True)
    totAmount = Column(Numeric(18, 2), nullable=True)    # EX/FOR Price = totRate + GST

    quotation = relationship("QuotSummary", back_populates="details")
    item = relationship("ItemName", foreign_keys=[itemid])


class QuotTermsNConditions(Base, AuditMixin):
    __tablename__ = "QuotTermsNConditions"

    quotTncId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)
    masterTncId = Column(Integer, ForeignKey("TermsNConditionMaster.tncId"), nullable=True)
    tncName = Column(String(200), nullable=True)
    tncDescription = Column(Text, nullable=True)
    sortOrder = Column(Integer, default=0, nullable=False)

    quotation = relationship("QuotSummary", back_populates="terms")
    master_tnc = relationship("TermsNConditionMaster", foreign_keys=[masterTncId])


class QuotFollowUp(Base, AuditMixin):
    __tablename__ = "QuotFollowUp"

    quotfollowupid = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)
    followupdate = Column(Date, nullable=True)
    followupremarks = Column(String(500), nullable=True)
    followupmode = Column(String(50), nullable=True)
    nextfollowupdate = Column(Date, nullable=True)

    quotation = relationship("QuotSummary", foreign_keys=[quotId])
