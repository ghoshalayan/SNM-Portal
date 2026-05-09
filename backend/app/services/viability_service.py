"""Viability Sheet — generation, goal-seek, and per-line recompute.

A Viability Sheet is a snapshot of QuotDetails taken when a quotation is Matured.
Edits live in QuotViabilityLine and never mutate the working sheet (QuotDetails).
"""
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.item import ItemName
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import QuotDetails, QuotSummary
from app.services.costing_service import get_tp_cost_decimal
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
    # Decimal-native — drops the lossy Decimal→float→Decimal round-trip the
    # old `get_tp_cost_for_dia` introduced before C1's split. ``_d`` is now an
    # identity for Decimals.
    tp = get_tp_cost_decimal(db, line.companyId, new_dia)
    if tp is not None:
        line.TPWGST = _round2(tp)
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
    # Accept any status that indicates the quotation has reached
    # Convert or beyond — the function is idempotent and returns the
    # existing sheet on subsequent calls. The legacy strings are kept
    # in the set so rows still mid-migration also pass.
    allowed = {
        "Converted",
        "Matured",
        "ViabilityGenerated",
        "ViabilityApproved",
        "AnnexureGenerated",
        "AnnexureApproved",
    }
    if quotation.status not in allowed:
        raise ValueError("Viability sheet can only be generated from a Converted quotation.")

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

    # Phase 3 freshness pointer — record which PO version's working
    # sheet this viability snapshot was generated from. The frontend
    # uses this to detect "stale" viability when the PO is re-sourced
    # later and offer a Re-source action.
    po = quotation.purchase_order
    sourced_from_po_version = po.versionNo if po is not None else None

    sheet = QuotViabilitySheet(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        status="Draft",
        sourcedFromPOVersion=sourced_from_po_version,
        createdby=user_id,
    )
    db.add(sheet)
    db.flush()  # need viabilityId

    # Phase 1.5 source switch: prefer the PO's Final Working Sheet
    # (``QuotPOWorkingSheet``) when present — that's the canonical
    # post-Convert BOM. Fall back to ``QuotDetails`` for legacy
    # quotations whose POs were captured before the Final Working
    # Sheet existed (or for quotations that never reached Convert).
    from app.models.quot_po_working_sheet import QuotPOWorkingSheet
    detail_rows: List = []
    if po is not None:
        detail_rows = (
            db.query(QuotPOWorkingSheet)
            .filter(
                QuotPOWorkingSheet.quotPOId == po.quotPOId,
                QuotPOWorkingSheet.isActive == True,  # noqa: E712
            )
            .order_by(QuotPOWorkingSheet.poWorkingSheetId.asc())
            .all()
        )
    if not detail_rows:
        detail_rows = (
            db.query(QuotDetails)
            .filter(
                QuotDetails.quotId == quotation.quotId,
                QuotDetails.isActive == True,  # noqa: E712
            )
            .order_by(QuotDetails.quotDtlId.asc())
            .all()
        )

    # Resolve item names in one pass to avoid N queries
    item_ids = {d.itemid for d in detail_rows if d.itemid}
    name_map = {}
    if item_ids:
        name_map = {
            i.itemId: i.itemName
            for i in db.query(ItemName).filter(ItemName.itemId.in_(item_ids)).all()
        }

    for d in detail_rows:
        # ``sourceQuotDtlId`` traces back to the canonical quoted line.
        # When sourcing from QuotPOWorkingSheet, prefer its own
        # ``sourceQuotDtlId`` audit pointer; fall back to the row's own
        # PK only if it's already a QuotDetails row (legacy path).
        source_quot_dtl = (
            getattr(d, "sourceQuotDtlId", None)
            or getattr(d, "quotDtlId", None)
        )
        line = QuotViabilityLine(
            companyId=sheet.companyId,
            viabilityId=sheet.viabilityId,
            sourceQuotDtlId=source_quot_dtl,
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


# ---------------------------------------------------------------------------
# Phase 2 — Time-travel: list versions + restore past version
# ---------------------------------------------------------------------------

# Per-line columns cloned when restoring a past viability version. Same
# set as ``LINE_COPY_COLS`` plus computed/goal-seek + identity. Audit +
# PK + parent FK are set explicitly by ``restore_viability_version``.
_VIABILITY_LINE_CLONE_COLUMNS = (
    "sourceQuotDtlId", "itemid", "itemName", "itemGradeName", "itemDia",
    "itemLength", "itemUnit", "quantity", "orderedQty", "modeOfDispatch",
    "TPWGST", "Marketing", "FreightTrailer", "FreightTruck", "Unloading",
    "OHD", "IFC", "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge",
    "ShortLnthCharge", "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
    "Commission", "Misc", "Testing", "MOUTOD", "SplDisc", "JC",
    "basicRate", "totRate", "gstMode",
    "IGST", "CGST", "SGST", "totAmount",
    "totalAmount", "totalGst", "grossExForPrice",
    "targetTotRate", "adjustableHeads",
)


def re_source_viability_from_po(
    db: Session,
    quotation: QuotSummary,
    *,
    user_id: int,
) -> QuotViabilitySheet:
    """Re-source viability from the current PO head's working sheet.

    Use case: PO was re-sourced (or the user edited the PO Working
    Sheet via Unlock-and-Edit) and the existing viability snapshot
    is now out of date. This archives the current viability head
    and runs a fresh ``generate_viability_sheet`` against the new
    PO state, bumping the version chain.
    """
    current_head = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.isActive == True,  # noqa: E712
        )
        .first()
    )
    if current_head is not None:
        current_head.isActive = False
        current_head.lastupdateby = user_id
        db.flush()

    # Now ``generate_viability_sheet`` finds no active sheet and
    # creates a fresh one. Patch versionNo + parent + sourcedFrom to
    # chain it to the prior head.
    new_sheet = generate_viability_sheet(
        db, quotation=quotation, user_id=user_id,
    )

    max_version = (
        db.query(func.max(QuotViabilitySheet.versionNo))
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.viabilityId != new_sheet.viabilityId,
        )
        .scalar()
        or 0
    )
    chain_root = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.parentViabilityId.is_(None),
            QuotViabilitySheet.viabilityId != new_sheet.viabilityId,
        )
        .order_by(QuotViabilitySheet.versionNo.asc())
        .first()
    )
    new_sheet.versionNo = max_version + 1 if max_version else 1
    new_sheet.parentViabilityId = (
        chain_root.viabilityId if chain_root else None
    )
    db.flush()
    db.refresh(new_sheet)
    return new_sheet


def list_viability_versions(
    db: Session, quotation: QuotSummary,
) -> List[QuotViabilitySheet]:
    """Return every version of the viability chain attached to this
    quotation, head first. Includes archived (``isActive=False``) past
    versions for time-travel."""
    return (
        db.query(QuotViabilitySheet)
        .filter(QuotViabilitySheet.quotId == quotation.quotId)
        .order_by(QuotViabilitySheet.versionNo.desc())
        .all()
    )


def restore_viability_version(
    db: Session,
    quotation: QuotSummary,
    target_viability_id: int,
    *,
    user_id: int,
) -> QuotViabilitySheet:
    """Clone an archived viability sheet forward as a new head.
    Mirrors ``purchase_order_service.restore_po_version`` — archive
    current head, MAX-versionNo +1, clone header + lines under the
    new sheet ID, status='Draft'."""
    target = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.viabilityId == target_viability_id,
            QuotViabilitySheet.quotId == quotation.quotId,
        )
        .first()
    )
    if target is None:
        raise ValueError(
            f"Viability version {target_viability_id} not found on this quotation."
        )

    # Archive current head if any.
    current_head = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.isActive == True,  # noqa: E712
        )
        .first()
    )
    if current_head is not None:
        current_head.isActive = False
        current_head.lastupdateby = user_id
        db.flush()

    max_version = (
        db.query(func.max(QuotViabilitySheet.versionNo))
        .filter(QuotViabilitySheet.quotId == quotation.quotId)
        .scalar()
        or 0
    )
    chain_root = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.parentViabilityId.is_(None),
        )
        .order_by(QuotViabilitySheet.versionNo.asc())
        .first()
    )

    new_sheet = QuotViabilitySheet(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        parentViabilityId=chain_root.viabilityId if chain_root else None,
        versionNo=max_version + 1,
        status="Draft",
        createdby=user_id,
    )
    db.add(new_sheet)
    db.flush()

    # Clone the target's lines under the new sheet id.
    target_lines = (
        db.query(QuotViabilityLine)
        .filter(
            QuotViabilityLine.viabilityId == target.viabilityId,
            QuotViabilityLine.isActive == True,  # noqa: E712
        )
        .order_by(QuotViabilityLine.viabilityLineId.asc())
        .all()
    )
    for src in target_lines:
        clone = QuotViabilityLine(
            companyId=new_sheet.companyId,
            viabilityId=new_sheet.viabilityId,
            createdby=user_id,
            **{col: getattr(src, col, None) for col in _VIABILITY_LINE_CLONE_COLUMNS},
        )
        db.add(clone)
    db.flush()
    db.refresh(new_sheet)
    return new_sheet
