"""Viability Sheet — generation, goal-seek, and per-line recompute.

A Viability Sheet is a snapshot of QuotDetails taken when a quotation is Matured.
Edits live in QuotViabilityLine and never mutate the working sheet (QuotDetails).
"""
from datetime import date
from decimal import Decimal
from typing import Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.timezone import now_ist
from app.models.item import ItemName
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import QuotDetails, QuotSummary
from app.models.raw_material_cost import RawMaterialCost
from app.models.raw_material_cost_log import RawMaterialCostLog
from app.services.costing_service import get_tp_cost_decimal
from app.services.quotation_service import (
    COST_HEAD_COLS,
    DEDUCTED_COST_HEADS,
    sum_cost_heads,
)

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
    # totRate = sum of cost heads, with CD + SplDisc subtracted (CR #2 —
    # users enter discounts as positive values, the math deducts them).
    tot_rate = sum_cost_heads(line)
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


# ------------------------------------------------------------------ TP-Cost refresh
def refresh_sheet_tp_cost(
    db: Session,
    sheet: QuotViabilitySheet,
    mode: str,
    as_of_date: Optional[date],
    overwrite_all: bool,
) -> dict:
    """Re-pull TPWGST for every line on a viability sheet according to the
    chosen mode.

    Modes:
      * ``as_of_date``       — rate from RawMaterialCost effective on
                                ``as_of_date`` (NULL = today).
      * ``po_working_sheet`` — value frozen on the matching Final
                                Working Sheet line when the PO was
                                captured. No rate-table query at all;
                                we copy ``QuotPOWorkingSheet.TPWGST``
                                across via ``sourceQuotDtlId``.

    Per-line outcome:
      * ``updated``        — TPWGST changed; recompute_line ran.
      * ``no_change``      — same value as before, no write.
      * ``missing_rate``   — no source value found (no rate-table row
                              for the date, OR no matching FWS line
                              for ``po_working_sheet``). TPWGST is
                              left untouched; flagged for a UI warning.
      * ``skipped_manual`` — overwrite_all=False and TPWGST doesn't
                              match *any* historical RawMaterialCost
                              rate for that dia, so we assume the user
                              hand-tuned it. Caller confirms before
                              clobbering.

    Also persists the new ``tpCostMode`` + ``tpCostAsOfDate`` on the sheet
    so the toggle stays in sync on the next GET.
    """
    # Resolve where each line's new TPWGST comes from. For as_of_date we
    # parameterise the rate-table helper; for po_working_sheet we
    # preload a sourceQuotDtlId → FWS-row map so the per-line loop is
    # O(1).
    effective_date: Optional[date] = None
    fws_by_source: dict = {}

    if mode == "as_of_date":
        effective_date = as_of_date  # may be None → helper falls back to today
    elif mode == "po_working_sheet":
        from app.models.quot_po_working_sheet import QuotPOWorkingSheet
        from app.models.quot_purchase_order import QuotPurchaseOrder
        po = (
            db.query(QuotPurchaseOrder)
            .filter(
                QuotPurchaseOrder.quotId == sheet.quotId,
                QuotPurchaseOrder.isActive == True,  # noqa: E712
            )
            .first()
        )
        if po is None:
            raise ValueError(
                "No Purchase Order found for this quotation — cannot use PO Working Sheet TP Cost."
            )
        fws_rows = (
            db.query(QuotPOWorkingSheet)
            .filter(
                QuotPOWorkingSheet.quotPOId == po.quotPOId,
                QuotPOWorkingSheet.isActive == True,  # noqa: E712
            )
            .all()
        )
        fws_by_source = {
            f.sourceQuotDtlId: f
            for f in fws_rows
            if f.sourceQuotDtlId is not None
        }
        if not fws_by_source:
            raise ValueError(
                "No Final Working Sheet rows found for the PO — cannot pull TP Cost from PO."
            )
    else:
        raise ValueError(f"Unknown TP-Cost mode: {mode!r}")

    # Manual-edit detection: a row is "manually tuned" only if its
    # current TPWGST doesn't match *any* rate this dia has ever held —
    # both the current master row AND every value captured in the
    # historical log (oldCost + newCost). Without including the log,
    # lines auto-populated from a rate that has since been overwritten
    # in the master would be wrongly flagged as manually edited.
    rate_history_by_dia: dict[str, set] = {}

    def _line_is_manual(line_company_id: int, dia: str, val) -> bool:
        if val is None:
            return False
        if dia not in rate_history_by_dia:
            master_rows = (
                db.query(RawMaterialCost.tpcost)
                .filter(
                    RawMaterialCost.companyId == line_company_id,
                    RawMaterialCost.dia == dia,
                    RawMaterialCost.isActive == True,
                )
                .all()
            )
            log_rows = (
                db.query(
                    RawMaterialCostLog.oldCost,
                    RawMaterialCostLog.newCost,
                )
                .filter(
                    RawMaterialCostLog.companyId == line_company_id,
                    RawMaterialCostLog.dia == dia,
                )
                .all()
            )
            history = {_round2(_d(r[0])) for r in master_rows if r[0] is not None}
            for old_v, new_v in log_rows:
                if old_v is not None:
                    history.add(_round2(_d(old_v)))
                if new_v is not None:
                    history.add(_round2(_d(new_v)))
            rate_history_by_dia[dia] = history
        return _round2(_d(val)) not in rate_history_by_dia[dia]

    per_line = []
    updated = 0
    skipped = 0
    missing = 0
    for line in sheet.lines:
        prev_val = line.TPWGST
        dia = line.itemDia
        if not dia:
            per_line.append({
                "viabilityLineId": line.viabilityLineId,
                "itemDia": dia,
                "previousTpwgst": prev_val,
                "newTpwgst": prev_val,
                "status": "no_change",
            })
            continue

        # The TPWGST the row *should* have under the new mode.
        #   as_of_date       → query RawMaterialCost at effective_date.
        #   po_working_sheet → copy from the FWS row's TPWGST that we
        #                       preloaded above.
        if mode == "po_working_sheet":
            fws_row = fws_by_source.get(line.sourceQuotDtlId)
            new_rate = fws_row.TPWGST if fws_row is not None else None
        else:
            new_rate = get_tp_cost_decimal(db, line.companyId, dia, as_of=effective_date)
        if new_rate is None:
            missing += 1
            per_line.append({
                "viabilityLineId": line.viabilityLineId,
                "itemDia": dia,
                "previousTpwgst": prev_val,
                "newTpwgst": prev_val,
                "status": "missing_rate",
            })
            continue

        if not overwrite_all and _line_is_manual(line.companyId, dia, prev_val):
            skipped += 1
            per_line.append({
                "viabilityLineId": line.viabilityLineId,
                "itemDia": dia,
                "previousTpwgst": prev_val,
                "newTpwgst": prev_val,
                "status": "skipped_manual",
            })
            continue

        new_val = _round2(new_rate)
        if prev_val is not None and _d(prev_val) == new_val:
            per_line.append({
                "viabilityLineId": line.viabilityLineId,
                "itemDia": dia,
                "previousTpwgst": prev_val,
                "newTpwgst": new_val,
                "status": "no_change",
            })
            continue

        line.TPWGST = new_val
        recompute_line(line)
        updated += 1
        per_line.append({
            "viabilityLineId": line.viabilityLineId,
            "itemDia": dia,
            "previousTpwgst": prev_val,
            "newTpwgst": new_val,
            "status": "updated",
        })

    # Stamp the chosen mode on the sheet so the next GET reflects it.
    sheet.tpCostMode = mode
    sheet.tpCostAsOfDate = (
        as_of_date if mode == "as_of_date"
        else None  # Approval-dated mode doesn't carry a user-picked date.
    )

    return {
        "updatedCount": updated,
        "skippedManualCount": skipped,
        "missingRateCount": missing,
        "perLine": per_line,
    }


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
    # totRate already deducts CD/SplDisc — use the same helper here so
    # delta is sign-consistent with what the user sees on screen.
    current_tot = sum_cost_heads(line)
    delta = target - current_tot
    if delta == 0:
        line.targetTotRate = target
        line.adjustableHeads = ",".join(sorted(allowed))
        recompute_line(line)
        return line

    # Weights
    magnitudes = {h: abs(_d(getattr(line, h))) for h in allowed}
    total_mag = sum(magnitudes.values())

    # When allocating delta to a DEDUCTED head (CD, SplDisc), the head's
    # stored value moves *opposite* to totRate. To raise totRate by +X via
    # CD, we must reduce CD by X (or increase a normal head by X). The
    # sign helper inverts the allocation for deducted heads.
    def _signed(head: str, amt: Decimal) -> Decimal:
        return -amt if head in DEDUCTED_COST_HEADS else amt

    if total_mag == 0:
        share = delta / Decimal(len(allowed))
        for h in allowed:
            setattr(line, h, _round2(_d(getattr(line, h)) + _signed(h, share)))
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
            setattr(line, h, _round2(_d(getattr(line, h)) + _signed(h, allocation)))

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
    sourced_from_fws_snapshot_id: int | None = None,
    sourced_from_viability_snapshot_id: int | None = None,
) -> QuotViabilitySheet:
    """Clone QuotDetails into a new QuotViabilityLine set. Idempotent — returns
    the existing active sheet if one is already present for this quotation.

    Source resolution (Phase B of the soft-flow UX cleanup):
      * ``sourced_from_fws_snapshot_id`` → clone lines from a frozen FWS
        approval snapshot. Live FWS untouched.
      * ``sourced_from_viability_snapshot_id`` → clone lines from a past
        Viability approval snapshot. Lets the user iterate forward from
        any prior approved viability version. Mutually exclusive with
        the FWS snapshot id (caller should pass at most one).
      * Neither → legacy default: live FWS rows for the captured PO,
        fallback to ``QuotDetails`` for pre-cycle quotations.

    Existing-head semantics:
      * **No source specified** → idempotent. Draft head returns as-is;
        Approved head forks forward to a new Draft v+1 carrying the
        edited lines forward.
      * **Source specified + head exists** → "regenerate from source".
        The current head (Draft or Approved) is archived and a fresh
        Draft v+1 is built from the picked source. This is the path
        the UI's Generate dialog drives when the user explicitly picks
        a source.
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

    if (
        sourced_from_fws_snapshot_id is not None
        and sourced_from_viability_snapshot_id is not None
    ):
        raise ValueError(
            "Pick either an FWS version or a past Viability version "
            "as the source — not both.",
        )

    explicit_source = (
        sourced_from_fws_snapshot_id is not None
        or sourced_from_viability_snapshot_id is not None
    )

    # Cycle-scoped existing-head lookup (2026-05-22 fix). Cycle 2
    # generating viability must NOT find Cycle 1's head and clobber
    # it. Resolve the target cycle from the quotation's PO (post-
    # Convert, the PO always has the right cycle FK) and filter by
    # it. Falls back to the legacy quotation-wide lookup if no cycle
    # context can be resolved (truly legacy pre-Phase-1A data).
    target_po = quotation.purchase_order
    target_cycle_id = None
    if target_po is not None and target_po.quotOrderCycleId is not None:
        target_cycle_id = target_po.quotOrderCycleId
    else:
        from app.services.cycle_service import resolve_active_cycle_id
        target_cycle_id = resolve_active_cycle_id(db, quotation.quotId)

    existing_query = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quotation.quotId,
            QuotViabilitySheet.isActive == True,
        )
    )
    if target_cycle_id is not None:
        existing_query = existing_query.filter(
            QuotViabilitySheet.quotOrderCycleId == target_cycle_id,
        )
    existing = existing_query.first()
    if existing and not explicit_source:
        # No source picked — preserve legacy idempotent behaviour.
        if existing.status != "Approved":
            return existing
        # Approved head → fork to a fresh Draft version that inherits
        # the current head's edited lines.
        return _fork_approved_viability(db, quotation, existing, user_id=user_id)
    if existing and explicit_source:
        # User explicitly picked a source while a head exists — treat
        # as "regenerate from source": archive the current head and
        # build a fresh Draft v+1 below. The previous version stays
        # reachable via the version dropdown.
        existing.isActive = False
        existing.lastupdateby = user_id
        existing.lastupdateon = now_ist()
        db.flush()

    # Phase 3 freshness pointer — record which PO version's working
    # sheet this viability snapshot was generated from. The frontend
    # uses this to detect "stale" viability when the PO is re-sourced
    # later and offer a Re-source action.
    po = quotation.purchase_order
    sourced_from_po_version = po.versionNo if po is not None else None

    # Phase 1A — ``quotOrderCycleId`` is NOT NULL on QuotViabilitySheet.
    # Prefer the PO's cycle (always populated post-Convert via the
    # cycle-aware path); fall back to the quotation's active cycle
    # for paths that don't carry a PO ref. ``None`` is only valid for
    # truly legacy quotations whose Convert pre-dated Phase 1A — but
    # those should have been backfilled by the migration, so seeing
    # None here in production means something's off.
    from app.services.cycle_service import resolve_active_cycle_id
    cycle_id = (
        po.quotOrderCycleId if po is not None and po.quotOrderCycleId
        else resolve_active_cycle_id(db, quotation.quotId)
    )

    # When we archived a predecessor head above (regenerate-from-source
    # path), bump the version chain so the new draft is v+1, not v1.
    next_version = 1
    parent_viability_id: int | None = None
    if existing and explicit_source:
        max_version = (
            db.query(func.max(QuotViabilitySheet.versionNo))
            .filter(QuotViabilitySheet.quotId == quotation.quotId)
            .scalar()
            or 0
        )
        next_version = max_version + 1
        chain_root = (
            db.query(QuotViabilitySheet)
            .filter(
                QuotViabilitySheet.quotId == quotation.quotId,
                QuotViabilitySheet.parentViabilityId.is_(None),
            )
            .order_by(QuotViabilitySheet.versionNo.asc())
            .first()
        )
        parent_viability_id = (
            chain_root.viabilityId if chain_root else existing.viabilityId
        )

    sheet = QuotViabilitySheet(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        quotOrderCycleId=cycle_id,
        parentViabilityId=parent_viability_id,
        versionNo=next_version,
        status="Draft",
        sourcedFromPOVersion=sourced_from_po_version,
        createdby=user_id,
    )
    db.add(sheet)
    db.flush()  # need viabilityId

    # Resolve the row collection to clone from. Four paths:
    #
    #   1. ``sourced_from_viability_snapshot_id`` supplied → clone lines
    #      directly from a frozen Viability approval snapshot. Uses the
    #      viability-line column set (incl. goal-seek tracking + orderedQty)
    #      so iterations preserve the user's prior tuning.
    #   2. ``sourced_from_fws_snapshot_id`` supplied → use that frozen
    #      FWS snapshot's data. Non-destructive: live FWS stays as-is.
    #   3. PO present + live FWS rows exist → use live FWS (the canonical
    #      post-Convert BOM).
    #   4. Fallback → ``QuotDetails`` for legacy quotations.
    from app.models.quot_po_working_sheet import QuotPOWorkingSheet
    detail_rows: List = []
    if sourced_from_viability_snapshot_id is not None:
        # Path 1 — viability snapshot. Skips the generic detail_rows /
        # LINE_COPY_COLS pipeline because viability snapshot rows have a
        # different (richer) column shape — they carry goal-seek state,
        # explicit ``orderedQty``, etc. that the QuotDetails/FWS path
        # doesn't know about.
        import json
        from app.models.approval_snapshot import QuotViabilityApprovalSnapshot
        from app.services.approval_snapshot_service import _coerce_snapshot_value
        snap = (
            db.query(QuotViabilityApprovalSnapshot)
            .filter(
                QuotViabilityApprovalSnapshot.snapshotId
                    == sourced_from_viability_snapshot_id,
                QuotViabilityApprovalSnapshot.companyId == quotation.companyId,
                QuotViabilityApprovalSnapshot.isActive == True,  # noqa: E712
            )
            .first()
        )
        if snap is None:
            raise ValueError(
                f"Viability approval snapshot {sourced_from_viability_snapshot_id} not found.",
            )
        payload = json.loads(snap.snapshotData)
        snap_lines = payload.get("lines", []) or []
        line_columns = {c.key: c for c in QuotViabilityLine.__table__.columns}
        for row_data in snap_lines:
            kwargs: dict = {}
            for key, raw in row_data.items():
                if key in {
                    "viabilityLineId",
                    "createdon", "createdby", "lastupdateon", "lastupdateby",
                    "isActive", "companyId", "viabilityId",
                }:
                    continue
                col = line_columns.get(key)
                if col is None:
                    continue
                kwargs[key] = _coerce_snapshot_value(col, raw)
            line = QuotViabilityLine(
                companyId=sheet.companyId,
                viabilityId=sheet.viabilityId,
                createdby=user_id,
                **kwargs,
            )
            recompute_line(line)
            db.add(line)
        db.flush()
        db.refresh(sheet)
        return sheet
    if sourced_from_fws_snapshot_id is not None:
        # Path 1 — pinned FWS snapshot.
        import json
        from types import SimpleNamespace
        from app.models.approval_snapshot import QuotFWSApprovalSnapshot
        from app.services.approval_snapshot_service import _coerce_snapshot_value
        snap = (
            db.query(QuotFWSApprovalSnapshot)
            .filter(
                QuotFWSApprovalSnapshot.snapshotId == sourced_from_fws_snapshot_id,
                QuotFWSApprovalSnapshot.companyId == quotation.companyId,
                QuotFWSApprovalSnapshot.isActive == True,  # noqa: E712
            )
            .first()
        )
        if snap is None:
            raise ValueError(
                f"FWS approval snapshot {sourced_from_fws_snapshot_id} not found."
            )
        # Build proxy objects with the same attribute interface as
        # ``QuotPOWorkingSheet`` so the downstream copy loop (which
        # uses ``getattr(d, col, None)``) is happy. Decimal/date strings
        # get coerced to native types so ``recompute_line`` doesn't choke
        # on string-typed numerics.
        cols_by_name = {c.key: c for c in QuotPOWorkingSheet.__table__.columns}
        for row_data in json.loads(snap.snapshotData):
            coerced = {}
            for k, v in row_data.items():
                col = cols_by_name.get(k)
                coerced[k] = _coerce_snapshot_value(col, v) if col is not None else v
            detail_rows.append(SimpleNamespace(**coerced))
        # Tag the new sheet's source-version pointer with the snapshot
        # version so audit and the stale-banner logic can show
        # "sourced from FWS C{n}-V{m}".
        sourced_from_po_version = snap.versionNo
    elif po is not None:
        # Path 2 — live FWS for the captured PO.
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
        # Path 3 — legacy fallback.
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


def _fork_approved_viability(
    db: Session,
    quotation: QuotSummary,
    head: QuotViabilitySheet,
    *,
    user_id: int,
) -> QuotViabilitySheet:
    """Fork an Approved head into a fresh Draft v+1 carrying the same
    lines forward. Used by the re-Generate path: when the user clicks
    Generate on an already-approved sheet they want to iterate, not
    overwrite history. The previous head is archived (isActive=False)
    so the version dropdown can still time-travel back to it.

    Distinct from ``restore_viability_version``: that path forks an
    *archived* version forward; this one forks the current head.
    Sharing the implementation isn't worth the indirection — the
    archive-then-clone choreography differs subtly between the two.
    """
    head.isActive = False
    head.lastupdateby = user_id
    head.lastupdateon = now_ist()
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
        quotOrderCycleId=head.quotOrderCycleId,
        parentViabilityId=chain_root.viabilityId if chain_root else head.viabilityId,
        versionNo=max_version + 1,
        status="Draft",
        # Carry the source pointers forward so the stale banner keeps
        # working — the new draft is sourced from the same PO version
        # as the head it was forked from.
        sourcedFromPOVersion=head.sourcedFromPOVersion,
        tpCostMode=head.tpCostMode,
        tpCostAsOfDate=head.tpCostAsOfDate,
        createdby=user_id,
    )
    db.add(new_sheet)
    db.flush()

    head_lines = (
        db.query(QuotViabilityLine)
        .filter(
            QuotViabilityLine.viabilityId == head.viabilityId,
            QuotViabilityLine.isActive == True,  # noqa: E712
        )
        .order_by(QuotViabilityLine.viabilityLineId.asc())
        .all()
    )
    for src in head_lines:
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
        # New versions stay attached to the same cycle as the row
        # they're forked from — cycle scope is a property of the
        # viability chain, not of any individual version.
        quotOrderCycleId=target.quotOrderCycleId,
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
