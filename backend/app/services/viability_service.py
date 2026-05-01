"""Viability Sheet — generation, goal-seek, and per-line recompute.

A Viability Sheet is a snapshot of QuotDetails taken when a quotation is Matured.
Edits live in QuotViabilityLine and never mutate the working sheet (QuotDetails).
"""
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.item import ItemName
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import QuotDetails, QuotSummary
from app.services.costing_service import get_tp_cost_for_dia
from app.services.quotation_service import COST_HEAD_COLS

# Columns the user can touch during goal-seek. TPWGST is the base and never
# changes here — it only moves when the dia is refreshed.
ADJUSTABLE_HEADS: List[str] = [c for c in COST_HEAD_COLS if c != "TPWGST"]

# Columns on QuotDetails copied verbatim into a new QuotViabilityLine at
# generation time. (Cost heads + item/identity.) Gross + goal-seek columns
# are computed separately.
LINE_COPY_COLS: List[str] = [
    "itemid", "itemName", "itemGradeName", "itemDia", "itemLength", "itemUnit",
    "quantity", "modeOfDispatch",
    "basicRate", "totRate", "gstMode", "IGST", "CGST", "SGST", "totAmount",
    *COST_HEAD_COLS,
]


# ------------------------------------------------------------------ helpers
def _d(v) -> Decimal:
    """Coerce None/number to Decimal(0)."""
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


# ------------------------------------------------------------------ recompute
def recompute_line(line: QuotViabilityLine) -> QuotViabilityLine:
    """Recalculate totRate / GST / totAmount and the gross columns from the
    current per-MT cost heads + orderedQty. Safe to call repeatedly.
    """
    # totRate = sum of all cost heads (incl TPWGST)
    tot_rate = sum(_d(getattr(line, c)) for c in COST_HEAD_COLS)
    line.totRate = _round2(tot_rate) if tot_rate else None

    # GST — flat 18% to match existing quotation behaviour.
    gst_total = _round2(tot_rate * Decimal("0.18")) if tot_rate else Decimal("0")
    mode = (line.gstMode or "IGST").upper()
    if mode == "CGST_SGST":
        half = _round2(gst_total / Decimal("2"))
        line.IGST = None
        line.CGST = half
        line.SGST = gst_total - half  # keep rounding consistent
    else:
        line.IGST = gst_total if tot_rate else None
        line.CGST = None
        line.SGST = None

    # EX/FOR per MT (incl GST)
    line.totAmount = _round2(tot_rate + gst_total) if tot_rate else None

    # Gross (per-line aggregates)
    qty = _d(line.orderedQty)
    if qty and tot_rate:
        line.totalAmount = _round2(tot_rate * qty)
        line.totalGst = _round2(gst_total * qty)
        line.grossExForPrice = _round2(_d(line.totAmount) * qty)
    else:
        line.totalAmount = None
        line.totalGst = None
        line.grossExForPrice = None

    return line


# ------------------------------------------------------------------ dia refresh
def refresh_tpwgst_for_dia(
    db: Session, line: QuotViabilityLine, new_dia: Optional[str]
) -> QuotViabilityLine:
    """Pull latest effective TPWGST from RawMaterialCost for the new dia.
    If no rate is found we leave TPWGST untouched and still update the dia label.
    """
    line.itemDia = new_dia
    if not new_dia:
        return line
    tp = get_tp_cost_for_dia(db, line.companyId, new_dia)
    if tp is not None:
        line.TPWGST = _round2(_d(tp))
    recompute_line(line)
    return line


# ------------------------------------------------------------------ goal-seek
def apply_goal_seek(
    line: QuotViabilityLine,
    target: Decimal,
    adjustable_heads: Iterable[str],
) -> QuotViabilityLine:
    """Distribute (target − current totRate) across the named heads.

    Distribution rule:
      * 1 head selected → it absorbs the full delta.
      * N heads selected → delta is split proportional to each head's |current value|.
      * All selected heads at zero → split equally.
    We never clamp signs — a negative head can go positive if that's what it
    takes to hit the target, so the user can sanity-check the preview before
    saving.
    """
    allowed = {h for h in adjustable_heads if h in ADJUSTABLE_HEADS}
    if not allowed:
        raise ValueError("At least one adjustable head must be selected.")

    target = _d(target)
    current_tot = sum(_d(getattr(line, c)) for c in COST_HEAD_COLS)
    delta = target - current_tot
    if delta == 0:
        line.targetTotRate = target
        line.adjustableHeads = ",".join(sorted(allowed))
        recompute_line(line)
        return line

    # Weights
    magnitudes = {h: abs(_d(getattr(line, h))) for h in allowed}
    total_mag = sum(magnitudes.values())

    if total_mag == 0:
        share = delta / Decimal(len(allowed))
        for h in allowed:
            setattr(line, h, _round2(_d(getattr(line, h)) + share))
    else:
        running = Decimal("0")
        heads_sorted = sorted(allowed)  # deterministic residual allocation
        for idx, h in enumerate(heads_sorted):
            weight = magnitudes[h] / total_mag
            if idx == len(heads_sorted) - 1:
                # Last head absorbs rounding residual so the math is exact.
                allocation = delta - running
            else:
                allocation = _round2(delta * weight)
                running += allocation
            setattr(line, h, _round2(_d(getattr(line, h)) + allocation))

    line.targetTotRate = target
    line.adjustableHeads = ",".join(sorted(allowed))
    recompute_line(line)
    return line


# ------------------------------------------------------------------ generation
def generate_viability_sheet(
    db: Session,
    *,
    quotation: QuotSummary,
    user_id: int,
) -> QuotViabilitySheet:
    """Clone QuotDetails into a new QuotViabilityLine set. Idempotent — returns
    the existing active sheet if one is already present for this quotation.
    """
    # Accept any status that indicates the quotation has reached maturity or
    # beyond — the function is idempotent and returns the existing sheet on
    # subsequent calls, so broader acceptance here avoids spurious 400s once
    # the quotation has progressed past 'Matured' into viability/annexure
    # stages.
    allowed = {
        "Matured",
        "ViabilityGenerated",
        "ViabilityApproved",
        "AnnexureGenerated",
        "AnnexureApproved",
    }
    if quotation.status not in allowed:
        raise ValueError("Viability sheet can only be generated from a Matured quotation.")

    existing = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.isActive == True,
        )
        .first()
    )
    if existing:
        return existing

    sheet = QuotViabilitySheet(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        status="Draft",
        createdby=user_id,
    )
    db.add(sheet)
    db.flush()  # need viabilityId

    # Resolve item names in one pass to avoid N queries
    detail_rows: List[QuotDetails] = (
        db.query(QuotDetails)
        .filter(
            QuotDetails.quotId == quotation.quotId,
            QuotDetails.isActive == True,
        )
        .order_by(QuotDetails.quotDtlId.asc())
        .all()
    )
    item_ids = {d.itemid for d in detail_rows if d.itemid}
    name_map = {}
    if item_ids:
        name_map = {
            i.itemId: i.itemName
            for i in db.query(ItemName).filter(ItemName.itemId.in_(item_ids)).all()
        }

    for d in detail_rows:
        line = QuotViabilityLine(
            companyId=sheet.companyId,
            viabilityId=sheet.viabilityId,
            sourceQuotDtlId=d.quotDtlId,
            # defaults
            orderedQty=d.quantity,
            itemName=d.itemName or name_map.get(d.itemid),
            createdby=user_id,
        )
        for col in LINE_COPY_COLS:
            if col in ("itemName",):
                continue
            setattr(line, col, getattr(d, col, None))
        recompute_line(line)
        db.add(line)

    db.flush()
    db.refresh(sheet)
    return sheet
