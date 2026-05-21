"""Pydantic schemas for the LOI/Cycle endpoints (Phase 1C)."""
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, model_validator

from app.schemas.quot_purchase_order import QuotPurchaseOrderResponse


class InheritancePreviewResponse(BaseModel):
    """What a new cycle's Final Working Sheet WOULD inherit if started
    against a given parent cycle. Frontend renders this in the Start
    New Call-off confirm dialog so the user sees the source up front.

    ``sourceType`` is one of:
      * ``viability`` — parent has an Approved viability sheet; new
        cycle inherits its rates (preferred, CR decision C4).
      * ``working_sheet`` — parent has only a WS (no approved viability);
        new cycle inherits WS rates.
      * ``none`` — parent has neither; new cycle starts empty.
    """
    parentCycleId: int
    parentCycleNo: int
    sourceType: Literal["viability", "working_sheet", "none"]
    lineCount: int


class CycleStartRequest(BaseModel):
    """Body for ``POST /quotations/{id}/cycles`` — explicit "Start
    New Call-off". ``parentCycleId`` is optional — when omitted the
    service auto-resolves the most recent previous cycle as parent."""
    parentCycleId: Optional[int] = None
    notes: Optional[str] = None


class CycleCloseRequest(BaseModel):
    """Body for ``POST /cycles/{id}/close`` and ``/abandon``."""
    reason: Optional[str] = None


class CycleResponse(BaseModel):
    """Cycle envelope used by list + single-get endpoints. Pure
    metadata — no nested POs / viability / annexure. The bundle
    endpoint stitches those in via ``CycleBundleResponse`` below."""
    quotOrderCycleId: int
    companyId: int
    quotId: int
    cycleNo: int
    status: Literal["Active", "Complete", "Abandoned"]
    parentCycleId: Optional[int] = None
    startedOn: datetime
    startedBy: int
    closedOn: Optional[datetime] = None
    closedBy: Optional[int] = None
    notes: Optional[str] = None
    isActive: bool = True

    class Config:
        from_attributes = True


class CycleListResponse(BaseModel):
    """The full set of cycles for a quotation. Frontend renders the
    selector strip from this. Includes ``Active``, ``Complete``, and
    (when ``includeAbandoned=True``) ``Abandoned`` cycles."""
    cycles: List[CycleResponse]


class CycleBundleResponse(BaseModel):
    """One-shot fetch for the per-cycle workspace. Saves the frontend
    three round-trips when the user clicks a cycle pill."""
    cycle: CycleResponse
    purchaseOrders: List[QuotPurchaseOrderResponse] = []
    # Working sheet / viability / annexure shapes already exist in
    # their own schema files; the cycle bundle references their IDs +
    # statuses (lite) rather than re-exporting full rows. Frontend
    # fetches the full sheets on demand via existing endpoints.
    workingSheetLineCount: int = 0
    viabilityId: Optional[int] = None
    viabilityStatus: Optional[str] = None
    annexureId: Optional[int] = None
    annexureStatus: Optional[str] = None


class CycleHistoryResponse(BaseModel):
    """Every cycle on a quotation, each one stitched with its bundle.
    Phase 1F: backs the read-only Cycle History tab so the user can
    survey every call-off in one place without round-tripping per
    cycle. Includes abandoned cycles unconditionally — history view
    shows everything for context."""
    bundles: List[CycleBundleResponse] = []


class AppendPurchaseOrderRequest(BaseModel):
    """Body for ``POST /quotations/{qid}/cycles/{cId}/purchase-orders``.

    ``isLOI`` flips this row's flavour. ``poBody`` carries the
    customer-facing PO/LOI details — same shape used by the existing
    single-PO ``QuotPurchaseOrderBody``.
    """
    isLOI: bool = False
    # Inlined from QuotPurchaseOrderBody — duplicating the contract
    # here keeps OpenAPI generation cleaner than a deep nested model
    # when the frontend generates types from the spec.
    # ``poNo`` is optional: LOI captures may omit it (server auto-
    # generates ``LOI-{quotId}-{seq}``). The cross-field validator
    # below rejects missing poNo for formal POs.
    poNo: Optional[str] = None
    poDate: Any  # date or ISO string — Pydantic v2 coerces
    customerId: int
    customerContactId: Optional[int] = None
    billingSiteId: Optional[int] = None
    billingAddressManual: Optional[str] = None
    consigneeSiteId: Optional[int] = None
    consigneeAddressManual: Optional[str] = None
    remarks: Optional[str] = None
    # LOI-specific free-text body. Only meaningful when isLOI=True.
    loiText: Optional[str] = None

    def to_po_body(self):
        """Adapter — produce the canonical ``QuotPurchaseOrderBody``
        the PO service expects. Forwards isLOI + loiText so the
        downstream validator + persistence layer pick up the LOI
        flavour correctly (omitted previously, which broke LOI
        appends through this path)."""
        from app.schemas.quot_purchase_order import QuotPurchaseOrderBody
        return QuotPurchaseOrderBody(
            isLOI=self.isLOI,
            loiText=self.loiText,
            poNo=self.poNo, poDate=self.poDate, customerId=self.customerId,
            customerContactId=self.customerContactId,
            billingSiteId=self.billingSiteId,
            billingAddressManual=self.billingAddressManual,
            consigneeSiteId=self.consigneeSiteId,
            consigneeAddressManual=self.consigneeAddressManual,
            remarks=self.remarks,
        )

    @model_validator(mode="after")
    def _validate_lifecycle_safety(self):
        # No silent typecasting on isLOI — the route handler picks the
        # permission flag (CanCaptureLOI vs CanSubmitPO) on this.
        # Reject anything other than a real bool to avoid e.g.
        # isLOI="false" sliding through.
        if not isinstance(self.isLOI, bool):
            raise ValueError("isLOI must be a boolean")
        # poNo is only required for formal POs. LOIs may omit it —
        # the service auto-generates ``LOI-{quotId}-{seq}``.
        if not self.isLOI and not (self.poNo and self.poNo.strip()):
            raise ValueError("poNo is required when capturing a formal PO.")
        return self
