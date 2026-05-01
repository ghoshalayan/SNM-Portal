from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class QuotAnnexure(Base, AuditMixin):
    """Structured annexure document attached to a matured quotation.

    Populated from quotation + viability data at generation time; pure-manual
    fields (payment terms, delivery schedule, outstandings, etc.) are blank
    until the KRO fills them in.
    """
    __tablename__ = "QuotAnnexure"

    annexureId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)
    viabilityId = Column(Integer, ForeignKey("QuotViabilitySheet.viabilityId"), nullable=True)
    status = Column(String(20), default="Draft", nullable=False)

    # Header block
    clientName = Column(String(500), nullable=True)
    customerPONo = Column(String(50), nullable=True)
    customerPODate = Column(Date, nullable=True)
    totalBillableAmount = Column(Numeric(18, 2), nullable=True)
    totalQuantityMT = Column(Numeric(18, 2), nullable=True)

    # 25 body fields (1..25 in the PDF)
    invoicing = Column(String(200), nullable=True)                    # 1
    transportationMode = Column(String(50), nullable=True)            # 2: Trailer / Truck
    tcType = Column(String(50), nullable=True)                        # 3: Low Alloy / Normal
    paymentTerms = Column(Text, nullable=True)                        # 4
    loadabilityQty = Column(Numeric(18, 2), nullable=True)            # 5
    transportChargesPerMT = Column(Numeric(18, 2), nullable=True)     # 6
    transportChargesFOR = Column(String(500), nullable=True)          # 7
    specificLength = Column(String(200), nullable=True)               # 8
    tolerance = Column(String(200), nullable=True)                    # 9
    deliverySchedule = Column(Text, nullable=True)                    # 10
    transportRealizationPerMT = Column(Numeric(18, 2), nullable=True) # 11
    panNo = Column(String(50), nullable=True)                         # 12
    gstNo = Column(String(50), nullable=True)                         # 13
    contactPerson = Column(String(200), nullable=True)                # 14
    contactPersonNumber = Column(String(50), nullable=True)           # 15
    billingAddress = Column(Text, nullable=True)                      # 16
    consigneeAddress = Column(Text, nullable=True)                    # 17
    qualityFe = Column(String(50), nullable=True)                     # 18a
    qualityStandard = Column(String(50), nullable=True)               # 18b (IS-1786)
    qualityStandardLength = Column(String(200), nullable=True)        # 18c
    companyName = Column(String(100), nullable=True)                  # 19 (DGP)
    billsTo = Column(String(50), nullable=True)                       # 20 (SITE / HO)
    totalOutstanding = Column(Numeric(18, 2), nullable=True)          # 21
    overdueOutstanding = Column(Numeric(18, 2), nullable=True)        # 22
    diawiseBreakup = Column(Text, nullable=True)                      # 23 (JSON)
    unloadingScope = Column(String(50), nullable=True)                # 24a (CUSTOMER / SRMB)
    unloadingRate = Column(Numeric(18, 2), nullable=True)             # 24b
    remarks = Column(Text, nullable=True)                             # 25

    # Signatures
    preparedByUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    preparedByName = Column(String(200), nullable=True)
    checkedByUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    checkedByName = Column(String(200), nullable=True)
    approvedByUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    approvedByName = Column(String(200), nullable=True)
    approvedon = Column(DateTime, nullable=True)

    # Relationships
    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    viability = relationship("QuotViabilitySheet", foreign_keys=[viabilityId])
    prepared_by_user = relationship("User", foreign_keys=[preparedByUserId])
    checked_by_user = relationship("User", foreign_keys=[checkedByUserId])
    approved_by_user = relationship("User", foreign_keys=[approvedByUserId])
