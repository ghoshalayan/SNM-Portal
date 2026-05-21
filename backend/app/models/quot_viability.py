from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class QuotViabilitySheet(Base, AuditMixin):
    __tablename__ = "QuotViabilitySheet"

    viabilityId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)
    # LOI/Cycle CR — cycle grouping. Per-cycle scoping for WS / Viability /
    # Annexure was locked in the CR (C2). Nullable initially; backfill
    # flips to NOT NULL in the same migration.
    quotOrderCycleId = Column(
        Integer,
        ForeignKey("QuotOrderCycle.quotOrderCycleId"),
        nullable=True,
    )
    status = Column(String(20), default="Draft", nullable=False)
    approvedby = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    approvedon = Column(DateTime, nullable=True)
    # Per-stage versioning (Phase 1).
    parentViabilityId = Column(
        Integer, ForeignKey("QuotViabilitySheet.viabilityId"), nullable=True,
    )
    versionNo = Column(Integer, default=1, nullable=False)
    # Phase 3 source-version pointer.
    sourcedFromPOVersion = Column(Integer, nullable=True)

    # TP-Cost sourcing mode — drives where per-line TPWGST is pulled from
    # when the user clicks "Refresh TP Cost" or generates the sheet.
    #   'as_of_date' (default): use the rate effective on tpCostAsOfDate
    #                            (NULL = today).
    #   'approved_date'        : use the rate effective on the parent
    #                            quotation's approvedon date.
    # Persisted so reopening the sheet shows the same toggle position the
    # user last set.
    tpCostMode = Column(String(20), nullable=True)  # 'as_of_date' | 'approved_date'
    tpCostAsOfDate = Column(Date, nullable=True)

    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    approved_by_user = relationship("User", foreign_keys=[approvedby])
    lines = relationship(
        "QuotViabilityLine",
        back_populates="sheet",
        cascade="all, delete-orphan",
    )


class QuotViabilityLine(Base, AuditMixin):
    __tablename__ = "QuotViabilityLine"

    viabilityLineId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    viabilityId = Column(Integer, ForeignKey("QuotViabilitySheet.viabilityId"), nullable=False)
    sourceQuotDtlId = Column(Integer, ForeignKey("QuotDetails.quotDtlId"), nullable=True)

    # Identity
    itemid = Column(Integer, ForeignKey("ItemName.itemId"), nullable=True)
    itemName = Column(String(200), nullable=True)
    itemGradeName = Column(String(100), nullable=True)
    itemDia = Column(String(50), nullable=True)
    itemLength = Column(String(50), nullable=True)
    itemUnit = Column(String(20), nullable=True)
    quantity = Column(Numeric(18, 2), nullable=True)
    orderedQty = Column(Numeric(18, 2), nullable=True)
    modeOfDispatch = Column(String(200), nullable=True)

    # Cost heads (per MT)
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

    # Calculated + GST
    basicRate = Column(Numeric(18, 2), nullable=True)
    totRate = Column(Numeric(18, 2), nullable=True)
    gstMode = Column(String(20), default="IGST", nullable=True)
    IGST = Column(Numeric(18, 2), nullable=True)
    CGST = Column(Numeric(18, 2), nullable=True)
    SGST = Column(Numeric(18, 2), nullable=True)
    totAmount = Column(Numeric(18, 2), nullable=True)

    # Gross (computed from orderedQty)
    totalAmount = Column(Numeric(18, 2), nullable=True)       # totRate * orderedQty
    totalGst = Column(Numeric(18, 2), nullable=True)          # GST/MT * orderedQty
    grossExForPrice = Column(Numeric(18, 2), nullable=True)   # totAmount * orderedQty

    # Goal-seek trail (for audit / replay)
    targetTotRate = Column(Numeric(18, 2), nullable=True)
    adjustableHeads = Column(String(500), nullable=True)

    sheet = relationship("QuotViabilitySheet", back_populates="lines", foreign_keys=[viabilityId])
    source = relationship("QuotDetails", foreign_keys=[sourceQuotDtlId])
    item = relationship("ItemName", foreign_keys=[itemid])
