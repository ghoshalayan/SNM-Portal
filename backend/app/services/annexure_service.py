"""Annexure generation + helpers.

Builds a QuotAnnexure from the quotation + customer + approved viability
snapshot. Auto-populates every derivable field; pure-manual fields stay
blank for the KRO to fill in.
"""
import json
from collections import OrderedDict, Counter
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.customer import CustomerContacts, CustomerMaster, CustomerSite
from app.models.delivery import DeliveryMode
from app.models.quot_annexure import QuotAnnexure
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import QuotSummary, QuotTermsNConditions
from app.models.user import User


# Statuses at which the parent quotation must be before annexure can
# be generated. Under Phase 1 the lifecycle position past Convert is
# encoded in per-stage statuses, not on QuotSummary, so a Converted
# quotation with an Approved viability passes the gate. The legacy
# values stay in the set so any rows still mid-migration also pass.
VIABILITY_APPROVED_STATUSES = {
    "Converted",
    "ViabilityApproved", "AnnexureGenerated", "AnnexureApproved",
}


def _d(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _majority(values):
    """Return the most-common non-null value (ties → first one seen)."""
    seen = [v for v in values if v is not None and v != ""]
    if not seen:
        return None
    return Counter(seen).most_common(1)[0][0]


def compute_diawise_breakup(lines: List[QuotViabilityLine]) -> List[dict]:
    """Aggregate viability lines by dia → [{dia, qty, amount}]."""
    buckets: "OrderedDict[str, dict]" = OrderedDict()
    for line in lines:
        if not line.isActive:
            continue
        dia = line.itemDia or "-"
        b = buckets.setdefault(dia, {"dia": dia, "qty": Decimal("0"), "amount": Decimal("0")})
        b["qty"] += _d(line.orderedQty)
        b["amount"] += _d(line.grossExForPrice)
    # Coerce Decimal → float-serializable for JSON storage
    return [
        {"dia": b["dia"], "qty": float(b["qty"]), "amount": float(b["amount"])}
        for b in buckets.values()
    ]


def deserialize_breakup(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def generate_annexure(
    db: Session,
    *,
    quotation: QuotSummary,
    user_id: int,
) -> QuotAnnexure:
    """Idempotent — returns the existing active annexure if one already
    exists for this quotation.

    Pre-conditions:
      - quotation.status must indicate viability has been approved.
      - An active viability sheet with status='Approved' must exist.
    """
    if quotation.status not in VIABILITY_APPROVED_STATUSES:
        raise ValueError(
            f"Annexure can only be generated after the viability is approved "
            f"(quotation status is currently {quotation.status})."
        )

    existing = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotId == quotation.quotId,
            QuotAnnexure.isActive == True,
        )
        .first()
    )
    if existing:
        return existing

    viability = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.isActive == True,
        )
        .first()
    )
    if not viability or viability.status != "Approved":
        raise ValueError("An approved viability sheet is required before generating the annexure.")

    # The annexure header (customer name, GST/PAN, contact details,
    # billing & consignee addresses, PO no/date) all flow from the
    # Customer PO captured at the Approved → Matured transition. This
    # is what lets the annexure ship to a project site or bill a group
    # company even when the original quotation was prepped against the
    # customer's HO.
    po = quotation.purchase_order
    customer = (
        db.query(CustomerMaster).filter(CustomerMaster.customerId == po.customerId).first()
        if po else None
    )
    contact = (
        db.query(CustomerContacts)
        .filter(CustomerContacts.customerContactId == po.customerContactId)
        .first() if (po and po.customerContactId) else None
    )
    billing_site = (
        db.query(CustomerSite)
        .filter(CustomerSite.siteId == po.billingSiteId)
        .first() if (po and po.billingSiteId) else None
    )
    consignee_site = (
        db.query(CustomerSite)
        .filter(CustomerSite.siteId == po.consigneeSiteId)
        .first() if (po and po.consigneeSiteId) else None
    )
    # Tenant company — drives the "Company" line on the printed
    # annexure (item 19). Lookup via quotation.companyId rather than a
    # hardcoded brand string so each tenant prints its own name.
    company = (
        db.query(Company).filter(Company.companyId == quotation.companyId).first()
        if quotation.companyId else None
    )
    delivery_mode = (
        db.query(DeliveryMode)
        .filter(DeliveryMode.deliveryModeId == quotation.deliveryModeId)
        .first() if quotation.deliveryModeId else None
    )
    # Signature roles per business rule:
    #   * Prepared By (KRO) = the user who actually created the quotation
    #     row — i.e. ``createdby`` on ``QuotSummary``. They keyed in the
    #     line items, picked the customer, etc.
    #   * Checked By (HOD) = the quotation's ``ownerUserId`` — the user
    #     whose userCode is embedded in the quotNo (resolved at create
    #     time per the role's numGenMode). When numGenMode = own_code
    #     this is the same person as Prepared By; under parent_code /
    #     select_code it's the supervising HOD.
    owner_user = (
        db.query(User).filter(User.userId == quotation.ownerUserId).first()
        if quotation.ownerUserId else None
    )
    creator_user = (
        db.query(User).filter(User.userId == quotation.createdby).first()
        if quotation.createdby else None
    )

    # ----- Payment Terms auto-fill from T&C -----
    # Find the quotation's T&C row whose name reads as a payment term
    # (e.g. "Payment Terms", "Payment Schedule"). The description text is
    # the closest match to what the annexure's payment-terms field
    # expects to display, so seed it as the default. KRO can edit later.
    payment_terms_default: Optional[str] = None
    # ``nullslast`` isn't supported by SQL Server — emit a plain
    # ``ORDER BY sortOrder ASC, quotTncId ASC``. Rows with a null
    # sortOrder will sort first, which is acceptable: we only need any
    # one matching row, and the secondary key keeps the result
    # deterministic across calls.
    payment_tnc = (
        db.query(QuotTermsNConditions)
        .filter(
            QuotTermsNConditions.quotId == quotation.quotId,
            QuotTermsNConditions.companyId == quotation.companyId,
            QuotTermsNConditions.isActive == True,  # noqa: E712
            QuotTermsNConditions.tncName.ilike("%payment%"),
        )
        .order_by(
            QuotTermsNConditions.sortOrder.asc(),
            QuotTermsNConditions.quotTncId.asc(),
        )
        .first()
    )
    if payment_tnc:
        payment_terms_default = (
            payment_tnc.tncDescription or payment_tnc.tncName or None
        )

    active_lines = [l for l in viability.lines if l.isActive]

    # Aggregate totals
    total_qty = sum(_d(l.orderedQty) for l in active_lines)
    total_amount = sum(_d(l.grossExForPrice) for l in active_lines)

    # Transportation mode (default picks the stronger signal available)
    transport_mode = None
    if delivery_mode and delivery_mode.deliveryMode:
        dm = delivery_mode.deliveryMode.strip().lower()
        if "trailer" in dm:
            transport_mode = "Trailer"
        elif "truck" in dm:
            transport_mode = "Truck"
        else:
            transport_mode = delivery_mode.deliveryMode

    # Transport cost / MT → weighted avg of the freight head matching the mode.
    # Falls back to whichever head is populated when the mode is ambiguous.
    freight_total = Decimal("0")
    freight_qty = Decimal("0")
    for l in active_lines:
        qty = _d(l.orderedQty)
        if qty <= 0:
            continue
        freight = None
        if transport_mode == "Trailer":
            freight = l.FreightTrailer
        elif transport_mode == "Truck":
            freight = l.FreightTruck
        else:
            freight = l.FreightTrailer if l.FreightTrailer is not None else l.FreightTruck
        if freight is not None:
            freight_total += _d(freight) * qty
            freight_qty += qty
    transport_charges_per_mt = (freight_total / freight_qty) if freight_qty > 0 else None

    # Resolve the human-readable billing / consignee address for the
    # annexure header. Each can come from a saved CustomerSite (FK on
    # the PO) or from a free-text manual entry on the PO row when the
    # user opted not to save the address permanently.
    billing_address_text = (
        billing_site.addressLine if billing_site
        else (po.billingAddressManual if po else None)
    )
    consignee_address_text = (
        consignee_site.addressLine if consignee_site
        else (po.consigneeAddressManual if po else None)
    )
    # ``transportChargesFOR`` is the FOR delivery point — historically
    # it tracked the consignee (where freight terminates), so we keep
    # that semantic and seed it from the consignee site.
    transport_for_text = (
        consignee_site.addressLine if consignee_site
        else (consignee_site.siteAddressCode if consignee_site else None)
    ) or consignee_address_text

    annexure = QuotAnnexure(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        viabilityId=viability.viabilityId,
        status="Draft",
        # Phase 3 freshness pointers — record the upstream versions
        # this annexure was auto-filled from so the frontend can
        # detect when any of the three sources move past the stamp.
        sourcedFromQuotationVersion=quotation.versionNo,
        sourcedFromPOVersion=(po.versionNo if po else None),
        sourcedFromViabilityVersion=viability.versionNo,

        # Header — PO no/date and customer identity now come from the
        # captured PO, not the quotation row. None for any quotation
        # that somehow reaches annexure without a PO (shouldn't happen
        # given the status gate, but defensive).
        clientName=customer.customerName if customer else None,
        customerPONo=po.poNo if po else None,
        customerPODate=po.poDate if po else None,
        # Addressee defaults to the consignee address — the printed
        # annexure is, by definition, addressed to the entity receiving
        # the goods. KRO can override on the form before approval.
        addressedTo=consignee_address_text,
        totalBillableAmount=total_amount,
        totalQuantityMT=total_qty,

        # Static defaults — except ``companyName`` which now reflects
        # the actual tenant company (looked up by ``quotation.companyId``)
        # so the printed annexure carries the right brand on it.
        invoicing="Manufacturing",
        tolerance="No excess delivery",
        qualityStandard="IS-1786",
        companyName=(company.companyName if company else None),
        billsTo="HO",

        # Auto-derived
        transportationMode=transport_mode,
        transportChargesPerMT=transport_charges_per_mt,
        transportRealizationPerMT=transport_charges_per_mt,  # same as cost per user decision
        transportChargesFOR=transport_for_text,
        specificLength=_majority([l.itemLength for l in active_lines]),
        qualityFe=_majority([l.itemGradeName for l in active_lines]),
        qualityStandardLength=_majority([l.itemLength for l in active_lines]),

        panNo=customer.PAN if customer else None,
        gstNo=customer.GSTN if customer else None,
        contactPerson=contact.contactPersonName if contact else None,
        contactPersonNumber=(contact.officePhone or contact.personalPhone) if contact else None,
        billingAddress=billing_address_text,
        consigneeAddress=consignee_address_text,

        # Diawise breakup snapshot (JSON)
        diawiseBreakup=json.dumps(compute_diawise_breakup(active_lines)),

        # Pre-fill payment terms from the quotation's matching T&C row.
        # The KRO can override on the annexure form before approval.
        paymentTerms=payment_terms_default,

        # Signatures — Prepared By (KRO) is whoever actually created the
        # quotation row; Checked By (HOD) is the quotation owner (whose
        # userCode is in the quotNo, resolved per numGenMode at create
        # time). Names are stored as snapshots so historical annexures
        # stay readable even after a user is renamed / archived.
        preparedByUserId=quotation.createdby,
        preparedByName=creator_user.userName if creator_user else None,
        checkedByUserId=quotation.ownerUserId,
        checkedByName=owner_user.userName if owner_user else None,

        createdby=user_id,
    )
    db.add(annexure)
    db.flush()
    db.refresh(annexure)
    return annexure


# ---------------------------------------------------------------------------
# Phase 2 — Time-travel: list versions + restore past version
# ---------------------------------------------------------------------------

# Body columns cloned from a past annexure version into the restored
# head. Identity (annexureId), audit, status (becomes Draft), and
# parent/version pointers are set explicitly by ``restore_annexure_version``.
_ANNEXURE_CLONE_COLUMNS = (
    "viabilityId",
    "clientName", "customerPONo", "customerPODate",
    "totalBillableAmount", "totalQuantityMT", "addressedTo",
    "invoicing", "transportationMode", "tcType", "paymentTerms",
    "loadabilityQty", "transportChargesPerMT", "transportChargesFOR",
    "specificLength", "tolerance", "deliverySchedule",
    "transportRealizationPerMT",
    "panNo", "gstNo", "contactPerson", "contactPersonNumber",
    "billingAddress", "consigneeAddress",
    "qualityFe", "qualityStandard", "qualityStandardLength",
    "companyName", "billsTo",
    "totalOutstanding", "overdueOutstanding",
    "diawiseBreakup",
    "unloadingScope", "unloadingRate", "remarks",
    "preparedByUserId", "preparedByName",
    "checkedByUserId", "checkedByName",
)


def re_source_annexure_from_upstream(
    db: Session,
    *,
    quotation: QuotSummary,
    user_id: int,
) -> QuotAnnexure:
    """Re-source annexure from current quotation + PO + viability heads.

    Archive the current annexure head and run a fresh
    ``generate_annexure`` against the new upstream state. Updates
    parentAnnexureId + versionNo on the new row to chain to the
    previous head.
    """
    current_head = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotId == quotation.quotId,
            QuotAnnexure.isActive == True,  # noqa: E712
        )
        .first()
    )
    if current_head is not None:
        current_head.isActive = False
        current_head.lastupdateby = user_id
        db.flush()

    # ``generate_annexure`` is idempotent: with no active head, it
    # builds a fresh one from current upstream state.
    new_annexure = generate_annexure(
        db, quotation=quotation, user_id=user_id,
    )

    max_version = (
        db.query(func.max(QuotAnnexure.versionNo))
        .filter(
            QuotAnnexure.quotId == quotation.quotId,
            QuotAnnexure.annexureId != new_annexure.annexureId,
        )
        .scalar()
        or 0
    )
    chain_root = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotId == quotation.quotId,
            QuotAnnexure.parentAnnexureId.is_(None),
            QuotAnnexure.annexureId != new_annexure.annexureId,
        )
        .order_by(QuotAnnexure.versionNo.asc())
        .first()
    )
    new_annexure.versionNo = max_version + 1 if max_version else 1
    new_annexure.parentAnnexureId = (
        chain_root.annexureId if chain_root else None
    )
    db.flush()
    db.refresh(new_annexure)
    return new_annexure


def list_annexure_versions(
    db: Session, quotation: QuotSummary,
) -> List[QuotAnnexure]:
    """Return every version of the annexure chain attached to this
    quotation, head first. Includes archived past versions."""
    return (
        db.query(QuotAnnexure)
        .filter(QuotAnnexure.quotId == quotation.quotId)
        .order_by(QuotAnnexure.versionNo.desc())
        .all()
    )


def restore_annexure_version(
    db: Session,
    quotation: QuotSummary,
    target_annexure_id: int,
    *,
    user_id: int,
) -> QuotAnnexure:
    """Clone an archived annexure forward as a new head. Same shape
    as the PO + Viability restore helpers — archive current head,
    MAX-versionNo +1, copy body fields, set status='Draft'. Approval
    audit fields (``approvedByUserId / Name / on``) are deliberately
    NOT carried forward — the restored row is a fresh draft that
    needs re-sign-off."""
    target = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.annexureId == target_annexure_id,
            QuotAnnexure.quotId == quotation.quotId,
        )
        .first()
    )
    if target is None:
        raise ValueError(
            f"Annexure version {target_annexure_id} not found on this quotation."
        )

    current_head = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotId == quotation.quotId,
            QuotAnnexure.isActive == True,  # noqa: E712
        )
        .first()
    )
    if current_head is not None:
        current_head.isActive = False
        current_head.lastupdateby = user_id
        db.flush()

    max_version = (
        db.query(func.max(QuotAnnexure.versionNo))
        .filter(QuotAnnexure.quotId == quotation.quotId)
        .scalar()
        or 0
    )
    chain_root = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotId == quotation.quotId,
            QuotAnnexure.parentAnnexureId.is_(None),
        )
        .order_by(QuotAnnexure.versionNo.asc())
        .first()
    )

    new_row = QuotAnnexure(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        parentAnnexureId=chain_root.annexureId if chain_root else None,
        versionNo=max_version + 1,
        status="Draft",
        createdby=user_id,
        **{col: getattr(target, col, None) for col in _ANNEXURE_CLONE_COLUMNS},
    )
    db.add(new_row)
    db.flush()
    db.refresh(new_row)
    return new_row
