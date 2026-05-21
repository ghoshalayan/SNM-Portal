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
    # LOIs may omit poNo (service auto-generates). Formal POs MUST
    # carry the customer's reference — that's the field the AR team
    # matches invoices against later.
    if not body.isLOI and not (body.poNo or "").strip():
        raise PurchaseOrderValidationError("PO No is required.")
    if body.poDate is None:
        raise PurchaseOrderValidationError(
            "LOI Date is required." if body.isLOI else "PO Date is required.",
        )

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


def _resolve_po_no(
    db: Session, quotation: QuotSummary, body: QuotPurchaseOrderBody,
) -> str:
    """Produce the ``poNo`` to persist. For a formal PO this is just
    the user-supplied value, stripped. For an LOI we auto-generate
    ``LOI-{quotId}-{seq}`` where ``seq`` is one more than the count of
    existing LOI rows on the quotation — keeps the identifier short,
    stable, and unique per quotation without needing a separate
    sequence table."""
    if not body.isLOI:
        return (body.poNo or "").strip()
    existing_lois = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.isLOI == True,  # noqa: E712 — SQL Server BIT
        )
        .count()
    )
    return f"LOI-{quotation.quotId}-{existing_lois + 1}"


def get_po(db: Session, quotation: QuotSummary) -> Optional[QuotPurchaseOrder]:
    """Fetch the active PO for a quotation, or None when not yet captured.

    NB: cycle-blind. In the Phase-1B cycle world a quotation can have
    many active POs (multiple per cycle, multiple cycles). Callers that
    need the *currently-relevant* PO for a Stage-2 transition (Submit,
    Reject) should use :func:`get_submit_target_po` instead. This helper
    is kept on the surface for legacy single-cycle paths and reads where
    "any one PO" is acceptable (visibility checks, stale-banner lookups).
    """
    return (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quotation.quotId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )


def get_submit_target_po(
    db: Session, quotation: QuotSummary,
) -> Optional[QuotPurchaseOrder]:
    """Return the PO that the legacy Submit/Reject endpoints should act on.

    Resolution rule:

    * If the quotation has at least one **Active** cycle, scope to the
      latest one (highest ``cycleNo``) and return the head **formal** PO
      (``isLOI=False``) in that cycle. LOIs are ignored because Submit
      & Mature only applies to binding orders.
    * If there are no Active cycles, fall back to the legacy single-PO
      lookup so pre-cycle quotations keep working unchanged.

    The "head" within a cycle is the highest ``versionNo`` row — handles
    re-source / restore scenarios where multiple PO versions co-exist.

    Returning ``None`` is a legitimate "nothing to submit" signal — the
    caller maps it to a clear 4xx instead of corrupting state.
    """
    # Local import — the model is loaded at module level via __init__,
    # but pulling it in here keeps the dependency surface explicit.
    from app.models.quot_order_cycle import QuotOrderCycle

    active_cycle = (
        db.query(QuotOrderCycle)
        .filter(
            QuotOrderCycle.quotId == quotation.quotId,
            QuotOrderCycle.status == "Active",
            QuotOrderCycle.isActive == True,  # noqa: E712
        )
        .order_by(QuotOrderCycle.cycleNo.desc())
        .first()
    )

    q = db.query(QuotPurchaseOrder).filter(
        QuotPurchaseOrder.quotId == quotation.quotId,
        QuotPurchaseOrder.isActive == True,  # noqa: E712
        # LOIs are non-binding; Submit & Mature targets the formal PO.
        # ``isLOI`` is non-nullable on the model, so explicit-False is
        # the canonical exclusion.
        QuotPurchaseOrder.isLOI == False,  # noqa: E712
    )
    if active_cycle is not None:
        q = q.filter(
            QuotPurchaseOrder.quotOrderCycleId == active_cycle.quotOrderCycleId,
        )
    return q.order_by(QuotPurchaseOrder.versionNo.desc()).first()


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
    resolved_po_no = _resolve_po_no(db, quotation, body)
    # Whitespace-only loiText collapses to None so the DB doesn't
    # carry meaningless padding.
    loi_text = None
    if body.isLOI and body.loiText:
        stripped = body.loiText.strip()
        loi_text = stripped or None
    if existing is None:
        po = QuotPurchaseOrder(
            companyId=quotation.companyId,
            quotId=quotation.quotId,
            isLOI=bool(body.isLOI),
            loiText=loi_text,
            poNo=resolved_po_no,
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
    existing.poNo = resolved_po_no
    existing.poDate = body.poDate
    existing.customerId = body.customerId
    existing.customerContactId = body.customerContactId
    existing.billingSiteId = body.billingSiteId
    existing.billingAddressManual = (body.billingAddressManual or None)
    existing.consigneeSiteId = body.consigneeSiteId
    existing.consigneeAddressManual = (body.consigneeAddressManual or None)
    existing.remarks = (body.remarks or None)
    # LOI-specific fields — only set them on edit when the row is an
    # LOI; flipping a formal PO into an LOI mid-life makes no sense.
    if existing.isLOI:
        existing.loiText = loi_text
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

    Cycle-aware: when the quotation has an Active cycle, scopes to the
    formal-PO head of the latest one (see :func:`get_submit_target_po`).
    Pre-cycle quotations fall through to the legacy single-PO lookup
    inside that helper, so behaviour is unchanged for them.
    """
    po = get_submit_target_po(db, quotation)
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

    Cycle-aware: same scoping as :func:`submit_po` — picks the formal-PO
    head of the latest Active cycle, falling through to the legacy
    single-PO lookup for pre-cycle quotations.
    """
    po = get_submit_target_po(db, quotation)
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


# ----------------------------------------------------------------------
# LOI / Cycle CR — cycle-scoped helpers (Phase 1B)
# ----------------------------------------------------------------------
# These functions are ADDITIVE — the existing single-PO functions
# above (``get_po``, ``create_or_update_po``, ``submit_po``,
# ``reject_po``) keep working for legacy callers during the
# Phase 1C alias window. New callers (cycle-scoped endpoints) use
# the helpers below.

def list_purchase_orders_in_cycle(
    db: Session, cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
) -> list[QuotPurchaseOrder]:
    """Return every active PO + LOI row attached to a cycle, ordered
    by ``loiSequence`` then ``createdon``. The frontend's per-cycle
    Stage 2 list view renders against this.

    SQL Server doesn't support ``ORDER BY ... NULLS LAST`` natively;
    SQLAlchemy's ``nulls_last()`` emits raw SQL that pyodbc rejects
    with a syntax error. Emulate the same effect with a CASE column
    that promotes nulls to a higher value than any real sequence —
    portable across SQL Server, sqlite, PostgreSQL, etc."""
    from sqlalchemy import case
    return (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .order_by(
            case((QuotPurchaseOrder.loiSequence.is_(None), 1), else_=0),
            QuotPurchaseOrder.loiSequence.asc(),
            QuotPurchaseOrder.createdon.asc(),
        )
        .all()
    )


def append_purchase_order_to_cycle(
    db: Session,
    cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
    body: QuotPurchaseOrderBody,
    *,
    user_id: int,
    is_loi: bool = False,
) -> QuotPurchaseOrder:
    """Create a fresh PO or LOI row inside an Active cycle. **Append-only**
    per CR decision C3 — LOIs and POs always create a new row, never
    upgrade an existing one in place.

    ``loiSequence`` is auto-assigned as the next sequential integer
    among rows currently in the cycle, so the frontend can render
    them in a deterministic order.

    **Phase 1E rate inheritance**: when this is the FIRST PO/LOI on a
    child cycle (cycle has parentCycleId and no FWS rows yet), the
    helper clones the parent's last approved viability into the new
    cycle's Final Working Sheet — falling back to the parent's WS if
    no approved viability exists. Subsequent appends to the same cycle
    share the cloned rows (one WS per cycle, CR decision C2).
    """
    if cycle.status != "Active":
        raise PurchaseOrderConflictError(
            f"Cannot append to a cycle in status {cycle.status!r}; "
            "cycle must be Active."
        )
    # Sync the body's LOI flag with the caller's explicit kwarg so
    # ``_validate_body`` doesn't reject a None poNo when the route
    # forwarded ``is_loi=True`` but the body shape didn't carry the
    # flag (e.g. older clients that forgot to set it).
    if is_loi and not body.isLOI:
        body.isLOI = True
    _validate_body(db, body, company_id=cycle.companyId)

    next_seq = (
        db.query(func.max(QuotPurchaseOrder.loiSequence))
        .filter(
            QuotPurchaseOrder.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .scalar()
    ) or 0
    is_first_append = next_seq == 0

    # Resolve the poNo to persist. LOIs auto-generate; formal POs use
    # the customer-supplied reference. The resolver needs a quotation
    # object — we don't have one here, but we can hand it the cycle
    # via a small adapter since it only reads ``quotId``.
    _quot_adapter = type("_QA", (), {"quotId": cycle.quotId})()
    resolved_po_no = _resolve_po_no(db, _quot_adapter, body)
    # Whitespace-only loiText → None so the column doesn't carry padding.
    loi_text = None
    if body.isLOI and body.loiText:
        stripped = body.loiText.strip()
        loi_text = stripped or None

    po = QuotPurchaseOrder(
        companyId=cycle.companyId,
        quotId=cycle.quotId,
        quotOrderCycleId=cycle.quotOrderCycleId,
        isLOI=bool(is_loi),
        loiText=loi_text,
        loiSequence=next_seq + 1,
        status="Draft",
        poNo=resolved_po_no,
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

    # Auto-clone the parent's inheritance source into this cycle's
    # Final Working Sheet — but only for the FIRST append on a child
    # cycle. Subsequent appends inherit nothing (the shared WS is
    # already populated).
    if is_first_append and cycle.parentCycleId:
        _clone_parent_ws_into_new_cycle(db, cycle=cycle, owning_po=po, user_id=user_id)

    return po


def submit_po_in_cycle(
    db: Session,
    cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
    po_id: int,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Cycle-scoped Submit & Mature for a specific PO row.

    Unambiguous replacement for the legacy ``submit_po`` — caller passes
    the cycle (already validated against the quotation by the endpoint)
    and the exact ``quotPOId`` of the row to submit. No
    "guess which PO" lookups, so multi-cycle quotations don't trip on
    the wrong row.

    Pre-conditions (caller enforces RBAC + CanSubmitPO):
      * Cycle is ``Active``.
      * PO row belongs to this cycle, is the formal PO (``isLOI=False``),
        and is in ``Draft``.

    Effect: PO ``status`` flips to ``Submitted``. The quotation's
    overall ``Converted`` status is unchanged — it stays at Stage 2
    while at least one cycle has a live formal PO.
    """
    if cycle.status != "Active":
        raise PurchaseOrderConflictError(
            f"Cannot submit a PO in a cycle whose status is {cycle.status!r}; "
            "the cycle must be Active.",
        )

    po = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotPOId == po_id,
            QuotPurchaseOrder.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )
    if po is None:
        raise PurchaseOrderConflictError(
            "Purchase order not found in this cycle (or no longer active).",
        )
    if po.isLOI:
        raise PurchaseOrderConflictError(
            "LOIs are non-binding and cannot be submitted; capture a formal PO first.",
        )
    if po.status != "Draft":
        raise PurchaseOrderConflictError(
            f"PO is already {po.status}; only Draft POs can be submitted.",
        )

    po.status = "Submitted"
    po.lastupdateby = user_id
    db.flush()
    db.refresh(po)
    return po


def reject_po_in_cycle(
    db: Session,
    cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
    po_id: int,
    *,
    user_id: int,
) -> QuotPurchaseOrder:
    """Cycle-scoped Reject for a specific PO row.

    The quotation's ``Converted`` status is un-set (back to ``Approved``)
    only if no OTHER cycle on the same quotation still has a Submitted
    formal PO. This preserves the legacy single-cycle un-Convert
    behaviour while keeping the quotation Converted when a sibling
    cycle is still alive — important for the multi-cycle Phase-1B model.

    Pre-conditions (caller enforces RBAC + CanRejectPO):
      * PO row belongs to this cycle and is currently ``Submitted``.

    Effect:
      * PO ``status`` → ``Rejected``.
      * If no other Submitted formal PO exists on any cycle of this
        quotation: quotation status → ``Approved``; ``convertedOn /
        convertedBy`` cleared.
    """
    po = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotPOId == po_id,
            QuotPurchaseOrder.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )
    if po is None:
        raise PurchaseOrderConflictError(
            "Purchase order not found in this cycle (or no longer active).",
        )
    if po.status != "Submitted":
        raise PurchaseOrderConflictError(
            f"Only Submitted POs can be rejected (current: {po.status}).",
        )

    po.status = "Rejected"
    po.lastupdateby = user_id

    # Decide whether the quotation un-Converts. It does only when this
    # was the LAST Submitted formal PO across all cycles. Anything else
    # means another cycle still has a live binding order, so the
    # quotation legitimately stays Converted.
    other_submitted_exists = (
        db.query(QuotPurchaseOrder.quotPOId)
        .filter(
            QuotPurchaseOrder.quotId == cycle.quotId,
            QuotPurchaseOrder.quotPOId != po_id,
            QuotPurchaseOrder.status == "Submitted",
            QuotPurchaseOrder.isLOI == False,  # noqa: E712
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
        is not None
    )
    if not other_submitted_exists:
        quotation = (
            db.query(QuotSummary)
            .filter(QuotSummary.quotId == cycle.quotId)
            .first()
        )
        if quotation is not None:
            quotation.status = "Approved"
            quotation.convertedOn = None
            quotation.convertedBy = None
            quotation.lastupdateby = user_id

    db.flush()
    db.refresh(po)
    return po


def _clone_parent_ws_into_new_cycle(
    db: Session,
    *,
    cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
    owning_po: QuotPurchaseOrder,
    user_id: int,
) -> int:
    """Delegate to po_working_sheet_service.clone_working_sheet_for_new_cycle
    and log the line count for the activity stream. Wrapped here so the
    append-PO path doesn't import po_working_sheet_service at module
    load (avoids a circular import — that service references
    ``QuotPurchaseOrder`` in its signatures).

    Returns the number of rows cloned (0 if the parent had neither an
    approved viability nor a working sheet).
    """
    from app.models.quot_order_cycle import QuotOrderCycle
    from app.services.po_working_sheet_service import clone_working_sheet_for_new_cycle

    parent_cycle = (
        db.query(QuotOrderCycle)
        .filter(
            QuotOrderCycle.quotOrderCycleId == cycle.parentCycleId,
            QuotOrderCycle.isActive == True,  # noqa: E712
        )
        .first()
    )
    if parent_cycle is None:
        return 0
    cloned = clone_working_sheet_for_new_cycle(
        db,
        new_cycle=cycle,
        parent_cycle=parent_cycle,
        owning_po=owning_po,
        user_id=user_id,
    )
    return len(cloned)
