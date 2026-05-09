"""Purchase Order capture service.

Owns the validation + DB shape for ``QuotPurchaseOrder``. The route
handlers stay thin — they enforce RBAC + status preconditions, then call
in here for the business rules and the actual create/update.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import CustomerContacts, CustomerMaster, CustomerSite
from app.models.quot_purchase_order import QuotPurchaseOrder
from app.models.quotation import QuotSummary
from app.schemas.quot_purchase_order import QuotPurchaseOrderBody


# PO is editable while it is still a Stage 2 Draft (i.e. between the
# quotation's `Convert` and the PO's `Submit & Mature`). Once Submitted
# the row is locked — editing it post-Submit happens via the
# privileged Unlock-and-Edit escape valve, not the regular edit path.
# The Stage-1 status check is for the legacy callers (pre-Phase-1) who
# still gate on the quotation's status; both paths converge on "PO row
# is in Draft".
PO_EDITABLE_STATUSES = {"Matured", "Converted"}
PO_EDITABLE_PO_STATUSES = {"Draft"}


class PurchaseOrderValidationError(ValueError):
    """Raised for body validation problems. Translated to 400 at the
    route layer so the user sees a clear message."""


class PurchaseOrderConflictError(RuntimeError):
    """Raised when the PO is locked because the quotation has moved
    past Matured. Translated to 409."""


def _validate_body(db: Session, body: QuotPurchaseOrderBody, *, company_id: int) -> None:
    if not (body.poNo or "").strip():
        raise PurchaseOrderValidationError("PO No is required.")
    if body.poDate is None:
        raise PurchaseOrderValidationError("PO Date is required.")

    # Customer must exist + be in the same company tenant.
    cust = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == body.customerId,
        CustomerMaster.companyId == company_id,
        CustomerMaster.isActive == True,  # noqa: E712 — SQL Server compat
    ).first()
    if cust is None:
        raise PurchaseOrderValidationError(
            "Selected customer is not available in this company."
        )

    if body.customerContactId is not None:
        contact = db.query(CustomerContacts).filter(
            CustomerContacts.customerContactId == body.customerContactId,
            CustomerContacts.customerId == body.customerId,
            CustomerContacts.isActive == True,  # noqa: E712
        ).first()
        if contact is None:
            raise PurchaseOrderValidationError(
                "Selected contact does not belong to the chosen customer."
            )

    # Billing & consignee: exactly one of (siteId, addressManual) per pair.
    _validate_address_pair(
        db,
        site_id=body.billingSiteId,
        manual=body.billingAddressManual,
        customer_id=body.customerId,
        label="Billing",
    )
    _validate_address_pair(
        db,
        site_id=body.consigneeSiteId,
        manual=body.consigneeAddressManual,
        customer_id=body.customerId,
        label="Consignee",
    )


def _validate_address_pair(
    db: Session,
    *,
    site_id: Optional[int],
    manual: Optional[str],
    customer_id: int,
    label: str,
) -> None:
    has_site = site_id is not None
    has_manual = bool((manual or "").strip())
    if has_site and has_manual:
        raise PurchaseOrderValidationError(
            f"{label} address: pick a saved site OR enter a manual address — not both."
        )
    if not has_site and not has_manual:
        raise PurchaseOrderValidationError(
            f"{label} address is required (pick a saved site or enter manually)."
        )
    if has_site:
        site = db.query(CustomerSite).filter(
            CustomerSite.siteId == site_id,
            CustomerSite.customerId == customer_id,
            CustomerSite.isActive == True,  # noqa: E712
        ).first()
        if site is None:
            raise PurchaseOrderValidationError(
                f"{label} site does not belong to the chosen customer."
            )


def get_po(db: Session, quotation: QuotSummary) -> Optional[QuotPurchaseOrder]:
    """Fetch the active PO for a quotation, or None when not yet captured."""
    return (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )


def create_or_update_po(
    db: Session,
    quotation: QuotSummary,
    body: QuotPurchaseOrderBody,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Idempotent capture: returns the existing active PO row if one
    exists (and updates it in place), otherwise creates a fresh row.

    Caller is responsible for status preconditions:
      - On the rewritten ``mature`` endpoint: only call when
        ``quotation.status == 'Approved'`` (creation path).
      - On the edit endpoint: only call when
        ``quotation.status in PO_EDITABLE_STATUSES`` (update path).
    """
    _validate_body(db, body, company_id=quotation.companyId)

    existing = get_po(db, quotation)
    if existing is None:
        po = QuotPurchaseOrder(
            companyId=quotation.companyId,
            quotId=quotation.quotId,
            poNo=body.poNo.strip(),
            poDate=body.poDate,
            customerId=body.customerId,
            customerContactId=body.customerContactId,
            billingSiteId=body.billingSiteId,
            billingAddressManual=(body.billingAddressManual or None),
            consigneeSiteId=body.consigneeSiteId,
            consigneeAddressManual=(body.consigneeAddressManual or None),
            remarks=(body.remarks or None),
            createdby=user_id,
        )
        db.add(po)
        db.flush()
        db.refresh(po)
        return po

    # Update path — overwrite scalar fields. We deliberately do NOT
    # null out the FK side when the new payload uses the manual side
    # (and vice versa); the validation step above ensures exactly one
    # is populated, and we mirror that on the row.
    existing.poNo = body.poNo.strip()
    existing.poDate = body.poDate
    existing.customerId = body.customerId
    existing.customerContactId = body.customerContactId
    existing.billingSiteId = body.billingSiteId
    existing.billingAddressManual = (body.billingAddressManual or None)
    existing.consigneeSiteId = body.consigneeSiteId
    existing.consigneeAddressManual = (body.consigneeAddressManual or None)
    existing.remarks = (body.remarks or None)
    existing.lastupdateby = user_id
    db.flush()
    db.refresh(existing)
    return existing


def ensure_editable(quotation: QuotSummary) -> None:
    """Raises ``PurchaseOrderConflictError`` when the quotation has
    moved past Matured / Converted. Used by the edit endpoint only —
    the create path is gated by the route-layer ``status ==
    'Approved'`` check."""
    if quotation.status not in PO_EDITABLE_STATUSES:
        raise PurchaseOrderConflictError(
            f"PO can only be edited while the quotation is Matured / "
            f"Converted (current status: {quotation.status})."
        )


# ---------------------------------------------------------------------------
# Phase 1 lifecycle transitions
# ---------------------------------------------------------------------------

def submit_po(
    db: Session,
    quotation: QuotSummary,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Submit & Mature transition. Stage-2 forward gate.

    Pre-conditions (caller enforces RBAC + permission flag check):
      * Quotation is ``Converted``.
      * PO row exists and is in ``Draft``.

    Effect: PO ``status`` flips to ``Submitted``. The quotation
    stays at ``Converted`` (Stage 2 internal state changes do not
    propagate up to QuotSummary.status under the new model).
    """
    po = get_po(db, quotation)
    if po is None:
        raise PurchaseOrderConflictError(
            "No purchase order to submit — capture the PO first via Convert."
        )
    if po.status != "Draft":
        raise PurchaseOrderConflictError(
            f"PO is already {po.status}; only Draft POs can be submitted."
        )
    po.status = "Submitted"
    po.lastupdateby = user_id
    db.flush()
    db.refresh(po)
    return po


# ---------------------------------------------------------------------------
# Phase 2 — Time-travel: list versions + restore past version
# ---------------------------------------------------------------------------

# Header columns cloned from a past PO version into a freshly-restored
# head. Excludes audit + status + chain pointers (set by ``restore_po_version``
# itself) and excludes ``quotPOId`` (auto-PK on the new row).
_PO_CLONE_COLUMNS = (
    "poNo", "poDate",
    "customerId", "customerContactId",
    "billingSiteId", "billingAddressManual",
    "consigneeSiteId", "consigneeAddressManual",
    "remarks",
)


def list_po_versions(db: Session, quotation: QuotSummary) -> list[QuotPurchaseOrder]:
    """Return every version of the PO chain attached to this quotation,
    head first. Includes archived (``isActive=False``) past versions —
    that's the whole point of time-travel."""
    return (
        db.query(QuotPurchaseOrder)
        .filter(QuotPurchaseOrder.quotId == quotation.quotId)
        .order_by(QuotPurchaseOrder.versionNo.desc())
        .all()
    )


def restore_po_version(
    db: Session,
    quotation: QuotSummary,
    target_po_id: int,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Clone an archived PO version forward as a new head. Steps:

    1. Look up the target PO row and verify it belongs to this
       quotation chain (defensive — the route layer also checks).
    2. Find the current head and flip it to ``isActive=False``.
    3. Compute ``versionNo`` as MAX over the chain + 1.
    4. Insert a new row with the target's data, linked to the chain
       root via ``parentPOId``, ``status='Draft'``, ``isActive=True``.
    5. Clone the target's ``working_sheet`` rows under the new PO id
       so the restored head has its line items intact.
    """
    target = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotPOId == target_po_id,
            QuotPurchaseOrder.quotId == quotation.quotId,
        )
        .first()
    )
    if target is None:
        raise PurchaseOrderConflictError(
            f"PO version {target_po_id} not found on this quotation."
        )

    # Archive whichever row is currently active (if any).
    current_head = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )
    if current_head is not None:
        current_head.isActive = False
        current_head.lastupdateby = user_id
        db.flush()

    # New versionNo: MAX over the chain (any isActive) + 1.
    max_version = (
        db.query(func.max(QuotPurchaseOrder.versionNo))
        .filter(QuotPurchaseOrder.quotId == quotation.quotId)
        .scalar()
        or 0
    )

    # Chain root: the v1 row (parentPOId IS NULL) for this quotation.
    chain_root = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.parentPOId.is_(None),
        )
        .order_by(QuotPurchaseOrder.versionNo.asc())
        .first()
    )
    parent_id = chain_root.quotPOId if chain_root else None

    new_row = QuotPurchaseOrder(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        parentPOId=parent_id,
        versionNo=max_version + 1,
        status="Draft",
        createdby=user_id,
        **{col: getattr(target, col, None) for col in _PO_CLONE_COLUMNS},
    )
    db.add(new_row)
    db.flush()

    # Clone the target's working-sheet lines under the new PO id.
    # Defer-import to avoid a circular import with po_working_sheet_service.
    from app.models.quot_po_working_sheet import QuotPOWorkingSheet
    target_lines = (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.quotPOId == target.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .all()
    )
    line_clone_cols = (
        "sourceQuotDtlId",
        "itemid", "itemName", "itemGradeName", "itemDia",
        "itemLength", "itemUnit", "quantity",
        "TPWGST", "Marketing", "FreightTrailer", "FreightTruck",
        "Unloading", "OHD", "IFC", "WeighmentDiff", "CD",
        "SWECharge", "CRS", "IncCharge", "ShortLnthCharge",
        "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
        "Commission", "Misc", "Testing", "MOUTOD", "SplDisc", "JC",
        "modeOfDispatch",
        "basicRate", "totRate", "gstMode",
        "IGST", "CGST", "SGST", "totAmount",
    )
    for src in target_lines:
        clone = QuotPOWorkingSheet(
            companyId=new_row.companyId,
            quotPOId=new_row.quotPOId,
            createdby=user_id,
            **{col: getattr(src, col, None) for col in line_clone_cols},
        )
        db.add(clone)
    db.flush()
    db.refresh(new_row)
    return new_row


def re_source_po_from_quotation(
    db: Session,
    quotation: QuotSummary,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Re-source the PO from the current Quotation head.

    Called when ``po.sourcedFromQuotationVersion < quotation.versionNo``
    — i.e. the quotation has been Revised since the PO was Converted.
    Steps:

    1. Fetch the current head PO; copy its header fields.
    2. Archive the current head (``isActive = False``).
    3. Insert a fresh PO row, ``versionNo = MAX + 1``, ``status =
       'Draft'``, header cloned from the previous head, ``sourcedFrom
       QuotationVersion = quotation.versionNo`` (now-current).
    4. Re-clone the Final Working Sheet from the current quotation's
       ``QuotDetails`` — this is the whole point: the BOM refreshes.
    """
    current_head = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )
    if current_head is None:
        raise PurchaseOrderConflictError(
            "No active PO to re-source — capture one via Convert first."
        )

    # Snapshot header fields off the current head before flipping it.
    header = {col: getattr(current_head, col, None) for col in _PO_CLONE_COLUMNS}

    current_head.isActive = False
    current_head.lastupdateby = user_id
    db.flush()

    max_version = (
        db.query(func.max(QuotPurchaseOrder.versionNo))
        .filter(QuotPurchaseOrder.quotId == quotation.quotId)
        .scalar()
        or 0
    )
    chain_root = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.parentPOId.is_(None),
        )
        .order_by(QuotPurchaseOrder.versionNo.asc())
        .first()
    )

    new_row = QuotPurchaseOrder(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        parentPOId=chain_root.quotPOId if chain_root else None,
        versionNo=max_version + 1,
        status="Draft",
        sourcedFromQuotationVersion=quotation.versionNo,
        createdby=user_id,
        **header,
    )
    db.add(new_row)
    db.flush()

    # Re-clone working sheet from the CURRENT quotation's QuotDetails.
    # Defer-import to avoid the circular with po_working_sheet_service.
    from app.services import po_working_sheet_service
    po_working_sheet_service.clone_from_quotation(
        db, new_row, quotation, user_id=user_id,
    )
    db.refresh(new_row)
    return new_row


def reject_po(
    db: Session,
    quotation: QuotSummary,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Reject the captured PO. Stage-2 backward escape.

    Pre-conditions (caller enforces RBAC + permission flag check):
      * PO row is ``Submitted`` (only submitted POs can be rejected;
        a Draft PO can simply be deleted).
      * Quotation is ``Converted``.

    Effect: PO ``status`` flips to ``Rejected``, AND the quotation
    is un-Converted back to ``Approved`` (clearing convertedOn /
    convertedBy) so the user can Revise / re-Convert cleanly.
    """
    po = get_po(db, quotation)
    if po is None:
        raise PurchaseOrderConflictError("No purchase order to reject.")
    if po.status != "Submitted":
        raise PurchaseOrderConflictError(
            f"Only Submitted POs can be rejected (current: {po.status})."
        )
    po.status = "Rejected"
    po.lastupdateby = user_id
    quotation.status = "Approved"
    quotation.convertedOn = None
    quotation.convertedBy = None
    quotation.lastupdateby = user_id
    db.flush()
    db.refresh(po)
    return po
