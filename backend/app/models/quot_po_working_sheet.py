from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import AuditMixin


class QuotPOWorkingSheet(Base, AuditMixin):
    """The Final Working Sheet — line items as they actually appear on
    the customer's PO. Cloned from ``QuotDetails`` on Convert; mutable
    while the PO is in Draft; snapshotted on Submit & Mature; the
    Viability + Annexure generators source qty / cost-head totals
    from these rows (with ``QuotDetails`` as a fallback for legacy
    quotations whose POs never had a Final Working Sheet).

    Schema mirrors ``QuotDetails`` so the existing line-items grid
    component can be reused on the frontend with a different endpoint.
    Every cost head you see on ``QuotDetails`` exists here too — keep
    them in sync if columns are added later.
    """
    __tablename__ = "QuotPOWorkingSheet"

    poWorkingSheetId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotPOId = Column(Integer, ForeignKey("QuotPurchaseOrder.quotPOId"), nullable=False)
    sourceQuotDtlId = Column(Integer, ForeignKey("QuotDetails.quotDtlId"), nullable=True)

    # Identity
    itemid = Column(Integer, ForeignKey("ItemName.itemId"), nullable=True)
    itemName = Column(String(200), nullable=True)
    itemGradeName = Column(String(100), nullable=True)
    itemDia = Column(String(50), nullable=True)
    itemLength = Column(String(50), nullable=True)
    itemUnit = Column(String(20), nullable=True)
    quantity = Column(Numeric(18, 2), nullable=True)

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

    modeOfDispatch = Column(String(200), nullable=True)

    # Calculated / GST
    basicRate = Column(Numeric(18, 2), nullable=True)
    totRate = Column(Numeric(18, 2), nullable=True)
    gstMode = Column(String(20), default="IGST", nullable=True)
    IGST = Column(Numeric(18, 2), nullable=True)
    CGST = Column(Numeric(18, 2), nullable=True)
    SGST = Column(Numeric(18, 2), nullable=True)
    totAmount = Column(Numeric(18, 2), nullable=True)

    purchase_order = relationship(
        "QuotPurchaseOrder",
        foreign_keys=[quotPOId],
        back_populates="working_sheet",
    )
    source_line = relationship("QuotDetails", foreign_keys=[sourceQuotDtlId])
    item = relationship("ItemName", foreign_keys=[itemid])
