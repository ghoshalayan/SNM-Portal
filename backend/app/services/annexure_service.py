"""Annexure generation + helpers.

Builds a QuotAnnexure from the quotation + customer + approved viability
snapshot. Auto-populates every derivable field; pure-manual fields stay
blank for the KRO to fill in.
"""
import json
from collections import OrderedDict, Counter
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.customer import CustomerContacts, CustomerMaster, CustomerSite
from app.models.delivery import DeliveryMode
from app.models.quot_annexure import QuotAnnexure
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import QuotSummary, QuotTermsNConditions
from app.models.user import User


# Statuses at which viability must be before annexure can be generated.
VIABILITY_APPROVED_STATUSES = {"ViabilityApproved", "AnnexureGenerated", "AnnexureApproved"}


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

    # Load related data for auto-population
    customer = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == quotation.customerId
    ).first()
    contact = (
        db.query(CustomerContacts)
        .filter(CustomerContacts.customerContactId == quotation.customerContactId)
        .first() if quotation.customerContactId else None
    )
    site = (
        db.query(CustomerSite)
        .filter(CustomerSite.siteId == quotation.siteId)
        .first() if quotation.siteId else None
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

    annexure = QuotAnnexure(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        viabilityId=viability.viabilityId,
        status="Draft",

        # Header
        clientName=customer.customerName if customer else None,
        customerPONo=quotation.CustomerPONo,
        customerPODate=quotation.CustomerPODate,
        totalBillableAmount=total_amount,
        totalQuantityMT=total_qty,

        # Static defaults
        invoicing="Manufacturing",
        tolerance="No excess delivery",
        qualityStandard="IS-1786",
        companyName="DGP",
        billsTo="HO",

        # Auto-derived
        transportationMode=transport_mode,
        transportChargesPerMT=transport_charges_per_mt,
        transportRealizationPerMT=transport_charges_per_mt,  # same as cost per user decision
        transportChargesFOR=(site.addressLine if site else None) or (site.siteAddressCode if site else None),
        specificLength=_majority([l.itemLength for l in active_lines]),
        qualityFe=_majority([l.itemGradeName for l in active_lines]),
        qualityStandardLength=_majority([l.itemLength for l in active_lines]),

        panNo=customer.PAN if customer else None,
        gstNo=customer.GSTN if customer else None,
        contactPerson=contact.contactPersonName if contact else None,
        contactPersonNumber=(contact.officePhone or contact.personalPhone) if contact else None,
        billingAddress=contact.address if contact else None,
        consigneeAddress=site.addressLine if site else None,

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
