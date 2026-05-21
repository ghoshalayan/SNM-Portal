from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class QuotPurchaseOrder(Base, AuditMixin):
    """Customer Purchase Order (or LOI) received against an Approved quotation.

    With the LOI/Cycle CR, the v1 1:1-with-QuotSummary constraint is
    dropped: a quotation can carry N POs and N LOIs across multiple
    call-off cycles. The UNIQUE filtered index on quotId is removed
    by the same migration that adds the cycle FK.

    ``isLOI`` flags a row as a Letter of Intent (vs a formal PO).
    Either flavour can mature Stage 2 of its cycle via Submit & Mature.

    Customer / contact / billing / consignee default from the quotation but
    each is independently overridable to support group-company billing,
    project-site delivery, etc. For billing and consignee, exactly ONE of
    {siteId, addressManual} is populated — siteId binds to a saved
    CustomerSite (possibly an isAdHoc one), addressManual is a one-off
    free-text address that the user chose not to save.
    """
    __tablename__ = "QuotPurchaseOrder"

    quotPOId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=False)

    # LOI/Cycle CR — grouping under a call-off cycle. Nullable initially
    # to ease the migration; flipped to NOT NULL after backfill.
    quotOrderCycleId = Column(
        Integer,
        ForeignKey("QuotOrderCycle.quotOrderCycleId"),
        nullable=True,
    )
    # True when this row is a Letter of Intent (non-binding qty
    # commitment) rather than a formal PO. Server-default 0 keeps
    # existing rows as POs.
    isLOI = Column(Boolean, default=False, nullable=False)
    # Display order of LOIs/POs within a cycle (1, 2, 3 …). Nullable
    # because legacy rows didn't have a cycle and don't need ordering.
    loiSequence = Column(Integer, nullable=True)

    # Per-stage versioning (Phase 1) — mirrors QuotSummary's chain
    # shape so any stage can carry independent revisions.
    parentPOId = Column(Integer, ForeignKey("QuotPurchaseOrder.quotPOId"), nullable=True)
    versionNo = Column(Integer, default=1, nullable=False)

    # Stage-2 lifecycle status. Independent from QuotSummary.status —
    # the parent quotation is `Converted` once it crosses Stage 1; the
    # PO row tracks Stage 2 internally.
    #   Draft      — capture in progress, mutable
    #   Submitted  — Submit & Mature fired; row is locked
    #   Rejected   — PO Reject fired; un-Converts quotation back to Approved
    status = Column(String(20), default="Draft", nullable=False)

    poNo = Column(String(50), nullable=False)
    poDate = Column(Date, nullable=False)

    customerId = Column(Integer, ForeignKey("CustomerMaster.customerId"), nullable=False)
    customerContactId = Column(
        Integer, ForeignKey("CustomerContacts.customerContactId"), nullable=True,
    )

    billingSiteId = Column(Integer, ForeignKey("CustomerSite.siteId"), nullable=True)
    billingAddressManual = Column(String(500), nullable=True)

    consigneeSiteId = Column(Integer, ForeignKey("CustomerSite.siteId"), nullable=True)
    consigneeAddressManual = Column(String(500), nullable=True)

    remarks = Column(String(500), nullable=True)

    # Free-text body of the LOI — the intent / scope language the
    # customer included in their letter of intent. Nullable; only
    # meaningful when ``isLOI = True``. Capped at 2000 chars to keep
    # the audit trail readable while leaving room for a paragraph or
    # two of commitment language.
    loiText = Column(String(2000), nullable=True)

    # Phase 3 source-version pointer — the QuotSummary.versionNo this
    # PO was Converted from. The frontend compares this to the current
    # quotation head to surface a "stale" banner when the quotation has
    # been Revised since this PO was captured.
    sourcedFromQuotationVersion = Column(Integer, nullable=True)

    quotation = relationship("QuotSummary", foreign_keys=[quotId], back_populates="purchase_order")
    customer = relationship("CustomerMaster", foreign_keys=[customerId])
    contact = relationship("CustomerContacts", foreign_keys=[customerContactId])
    billing_site = relationship("CustomerSite", foreign_keys=[billingSiteId])
    consignee_site = relationship("CustomerSite", foreign_keys=[consigneeSiteId])
    # Final Working Sheet rows — cloned from QuotDetails on Convert,
    # editable while PO=Draft, snapshotted on Submit. Source for
    # downstream viability + annexure generators.
    working_sheet = relationship(
        "QuotPOWorkingSheet",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        foreign_keys="QuotPOWorkingSheet.quotPOId",
    )
