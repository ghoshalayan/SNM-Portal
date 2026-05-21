"""Viability Sheet endpoints.

Flow:
  POST /quotations/{qid}/viability         → generate (idempotent)
  GET  /quotations/{qid}/viability         → bundle { workingSheet, viability }
  PUT  /viability/{vid}/lines/{lid}        → edit a line (recomputes server-side)
  POST /viability/{vid}/lines/{lid}/goal-seek
  PUT  /viability/{vid}/approve
  GET  /viability/{vid}/export             → XLSX (two sheets)

All endpoints tunnel through the Quotations access pipeline — a user who can
view a quotation can view its viability sheet; edit/approve require the
corresponding permission on the Quotations menu.
"""
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.timezone import now_ist
from app.models.approval_snapshot import QuotViabilityApprovalSnapshot
from app.models.quotation import QuotDetails, QuotSummary
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.schemas.approval_snapshot import (
    ViabilityApprovalSnapshotDetail,
    ViabilityApprovalSnapshotList,
    ViabilityApprovalSnapshotSummary,
)
from app.schemas.quot_viability import (
    ADJUSTABLE_HEADS,
    GoalSeekRequest,
    RefreshTpCostRequest,
    RefreshTpCostResponse,
    ViabilityBundleResponse,
    ViabilityLineResponse,
    ViabilityLineUpdate,
    ViabilitySheetResponse,
    WorkingSheetLine,
)
from app.services.access_service import (
    AccessContext,
    get_access_context,
    require_permission,
)
from app.services.viability_service import (
    apply_goal_seek,
    generate_viability_sheet,
    recompute_line,
    refresh_sheet_tp_cost,
    refresh_tpwgst_for_dia,
)
from app.services.activity_log_service import log_action, log_failure

MENU = "Quotations"

router = APIRouter()


# ------------------------------------------------------------------ helpers
def _get_quotation_or_403(db: Session, quot_id: int, ctx: AccessContext) -> QuotSummary:
    """Lightweight access check for the viability router. Falls back to a
    delayed import to avoid a cycle with quotations.py.
    """
    from app.api.v1.quotations import _get_quot_or_403  # noqa: WPS433
    return _get_quot_or_403(db, quot_id, ctx)


def _get_sheet_or_403(db: Session, viability_id: int, ctx: AccessContext) -> QuotViabilitySheet:
    sheet = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.viabilityId == viability_id,
            QuotViabilitySheet.isActive == True,
        )
        .first()
    )
    if not sheet:
        raise HTTPException(404, "Viability sheet not found")
    # Reuse quotation access check — the viability is pinned to a quotation.
    _get_quotation_or_403(db, sheet.quotId, ctx)
    return sheet


def _get_line_or_404(
    db: Session, viability_id: int, line_id: int
) -> QuotViabilityLine:
    line = (
        db.query(QuotViabilityLine)
        .filter(
            QuotViabilityLine.viabilityLineId == line_id,
            QuotViabilityLine.viabilityId == viability_id,
            QuotViabilityLine.isActive == True,
        )
        .first()
    )
    if not line:
        raise HTTPException(404, "Viability line not found")
    return line


def _ensure_editable(sheet: QuotViabilitySheet) -> None:
    """Soft-flow: this used to raise 400 when the sheet was Approved.
    Now it's a no-op — the row stays editable post-approval. Callers
    still invoke it as the explicit "editability check" point so that
    if we ever need to re-introduce a guard (e.g. a hard-freeze after
    cycle close), there's one obvious place to do it.

    Post-approval edits are journaled by :func:`_log_post_approval_edit`
    so the audit trail clearly records that the user touched a row
    that had already been signed off — the trade-off the soft-flow
    design accepted in place of locking.
    """
    return None


def _log_post_approval_edit(
    db: Session, sheet: QuotViabilitySheet, ctx, action: str, details: str | None = None,
) -> None:
    """Soft-flow audit marker: edits to an Approved sheet append an
    "edited after approval" entry on top of the regular action log.
    Callers run this in addition to (not instead of) their normal
    ``log_action`` call so reports can filter on the post-approval
    marker without losing the per-action history."""
    if sheet.status != "Approved":
        return
    from app.models.quotation import QuotSummary
    quotation = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
    log_action(
        db, quot_id=sheet.quotId, company_id=sheet.companyId,
        action=f"{action} (after approval)",
        status=quotation.status if quotation else None,
        ctx=ctx,
        details=details,
    )


def _load_working_sheet(db: Session, quot_id: int) -> List[WorkingSheetLine]:
    rows = (
        db.query(QuotDetails)
        .filter(
            QuotDetails.quotId == quot_id,
            QuotDetails.isActive == True,
        )
        .order_by(QuotDetails.quotDtlId.asc())
        .all()
    )
    return [WorkingSheetLine.model_validate(r) for r in rows]


def _bundle(db: Session, sheet: QuotViabilitySheet) -> ViabilityBundleResponse:
    sheet_resp = ViabilitySheetResponse(
        viabilityId=sheet.viabilityId,
        companyId=sheet.companyId,
        quotId=sheet.quotId,
        quotOrderCycleId=sheet.quotOrderCycleId,
        status=sheet.status,
        approvedby=sheet.approvedby,
        approvedon=sheet.approvedon,
        isActive=sheet.isActive,
        parentViabilityId=sheet.parentViabilityId,
        versionNo=sheet.versionNo,
        sourcedFromPOVersion=sheet.sourcedFromPOVersion,
        tpCostMode=sheet.tpCostMode,
        tpCostAsOfDate=sheet.tpCostAsOfDate,
        lines=[
            ViabilityLineResponse.model_validate(line)
            for line in sorted(sheet.lines, key=lambda x: x.viabilityLineId)
            if line.isActive
        ],
    )
    return ViabilityBundleResponse(
        workingSheet=_load_working_sheet(db, sheet.quotId),
        viability=sheet_resp,
        hasPoWorkingSheet=_has_po_working_sheet(db, sheet.quotId),
    )


def _has_po_working_sheet(db: Session, quot_id: int) -> bool:
    """True when the quotation has a PO with at least one active Final
    Working Sheet row — gates the "LTP on WS @PO" toggle option in the
    frontend.

    SQL Server doesn't accept ``SELECT EXISTS(...)`` as a top-level
    scalar expression (that's a PostgreSQL idiom), so we issue a plain
    ``SELECT TOP 1 poWorkingSheetId ...`` and bool-test the result.
    """
    from app.models.quot_po_working_sheet import QuotPOWorkingSheet
    from app.models.quot_purchase_order import QuotPurchaseOrder
    po = (
        db.query(QuotPurchaseOrder)
        .filter(
            QuotPurchaseOrder.quotId == quot_id,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
        )
        .first()
    )
    if not po:
        return False
    row = (
        db.query(QuotPOWorkingSheet.poWorkingSheetId)
        .filter(
            QuotPOWorkingSheet.quotPOId == po.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .first()
    )
    return row is not None


# ------------------------------------------------------------------ endpoints

class GenerateViabilityBody(BaseModel):
    """Optional source-picker payload for viability generation.

    All fields optional. Source resolution order (Phase B):
      * ``sourcedFromViabilitySnapshotId`` → clone from a past Viability
        approval snapshot (carries goal-seek state forward).
      * ``sourcedFromFWSSnapshotId`` → clone from a frozen FWS snapshot.
      * Neither → legacy live-FWS source.

    Picking both at once is rejected with a 400 — the user has to choose
    which type of source drives the regenerate.
    """
    sourcedFromFWSSnapshotId: int | None = None
    sourcedFromViabilitySnapshotId: int | None = None


@router.post("/quotations/{quot_id}/viability", response_model=ViabilityBundleResponse)
def create_viability(
    quot_id: int,
    body: GenerateViabilityBody | None = None,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Generate the viability sheet for a Converted quotation.

    Re-generation semantics (Phase 1 follow-up):
      * No existing head → create a fresh Draft sheet.
      * Draft head → idempotent: return the existing draft.
      * Approved head → fork forward as a new Draft v+1 carrying the
        previous version's edited lines (preserves goal-seek / TP
        refresh state). The old version is archived but stays
        time-travel reachable via the version dropdown.

    Slice B: optional body ``sourcedFromFWSSnapshotId`` pins the
    generation to a specific approved FWS snapshot. When omitted the
    legacy live-FWS path runs.
    """
    try:
        require_permission(MENU, "CanEdit", ctx)
        quotation = _get_quotation_or_403(db, quot_id, ctx)
        fws_snap_id = body.sourcedFromFWSSnapshotId if body is not None else None
        viab_snap_id = body.sourcedFromViabilitySnapshotId if body is not None else None
        try:
            sheet = generate_viability_sheet(
                db, quotation=quotation, user_id=ctx.user_id,
                sourced_from_fws_snapshot_id=fws_snap_id,
                sourced_from_viability_snapshot_id=viab_snap_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

        # Phase 1: per-stage statuses are the source of truth for the
        # lifecycle position past Convert. The quotation stays at
        # ``Converted``; the new viability sheet's own ``status``
        # ('Draft' on creation) tells the workspace where Stage 3 sits.
        if quotation.status == "Converted":
            log_action(db, quot_id=quotation.quotId, company_id=quotation.companyId,
                       action="Viability Sheet Generated", status=quotation.status,
                       user_id=ctx.user_id)

        db.commit()
        db.refresh(sheet)
        return _bundle(db, sheet)
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Generate Viability", user_id=ctx.user_id, exc=e)
        raise


@router.get("/quotations/{quot_id}/viability", response_model=ViabilityBundleResponse)
def get_viability(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Return the working sheet snapshot + the current viability sheet (if any).
    The viability field is null when not yet generated.
    """
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)

    sheet = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotId == quot_id,
            QuotViabilitySheet.isActive == True,
        )
        .first()
    )
    if not sheet:
        # Return working sheet only; client uses this to render the "Generate" CTA
        return {
            "workingSheet": _load_working_sheet(db, quot_id),
            "viability": None,
            "hasPoWorkingSheet": _has_po_working_sheet(db, quot_id),
        }
    return _bundle(db, sheet)


@router.put("/viability/{viability_id}/lines/{line_id}", response_model=ViabilityLineResponse)
def update_line(
    viability_id: int,
    line_id: int,
    body: ViabilityLineUpdate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)
    _ensure_editable(sheet)
    line = _get_line_or_404(db, viability_id, line_id)

    data = body.model_dump(exclude_unset=True)

    # Dia change triggers a TPWGST refresh from RawMaterialCost.
    new_dia = data.pop("itemDia", None) if "itemDia" in data else None
    explicit_tpwgst = "TPWGST" in data

    # Apply every other supplied field first
    for k, v in data.items():
        setattr(line, k, v)

    # If dia changed and user did not explicitly override TPWGST, refresh from master.
    if new_dia is not None and not explicit_tpwgst:
        refresh_tpwgst_for_dia(db, line, new_dia)
    elif new_dia is not None:
        # dia changed but TPWGST explicitly set — honour user value, just update label
        line.itemDia = new_dia

    line.lastupdateby = ctx.user_id
    line.lastupdateon = now_ist()
    recompute_line(line)
    # Narrow the log by intent: a dia change is usually a deliberate act that
    # triggers downstream rate refresh, so it gets its own label.
    if new_dia is not None:
        action_label = "Viability line dia refreshed"
        detail = f"lineId={line_id} · new dia {new_dia}"
    else:
        action_label = "Viability line edited"
        fields = list(data.keys())
        detail = f"lineId={line_id} · fields: {', '.join(fields)}" if fields else f"lineId={line_id}"
    from app.models.quotation import QuotSummary
    quotation = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
    log_action(db, quot_id=sheet.quotId, company_id=sheet.companyId,
               action=action_label,
               status=quotation.status if quotation else None,
               ctx=ctx,
               details=detail)
    _log_post_approval_edit(db, sheet, ctx, action_label, detail)
    db.commit()
    db.refresh(line)
    return line


@router.post(
    "/viability/{viability_id}/lines/{line_id}/goal-seek",
    response_model=ViabilityLineResponse,
)
def goal_seek(
    viability_id: int,
    line_id: int,
    body: GoalSeekRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)
    _ensure_editable(sheet)
    line = _get_line_or_404(db, viability_id, line_id)

    # Guard against typo'd head names client-side so we don't silently ignore.
    unknown = [h for h in body.adjustableHeads if h not in ADJUSTABLE_HEADS]
    if unknown:
        raise HTTPException(400, f"Unknown cost heads: {', '.join(unknown)}")

    try:
        apply_goal_seek(line, Decimal(body.target), body.adjustableHeads)
    except ValueError as e:
        raise HTTPException(400, str(e))

    line.lastupdateby = ctx.user_id
    line.lastupdateon = now_ist()
    from app.models.quotation import QuotSummary
    quotation = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
    gs_detail = (
        f"lineId={line_id} · target={body.target} · "
        f"heads: {', '.join(body.adjustableHeads)}"
    )
    log_action(db, quot_id=sheet.quotId, company_id=sheet.companyId,
               action="Viability goal-seek applied",
               status=quotation.status if quotation else None,
               ctx=ctx,
               details=gs_detail)
    _log_post_approval_edit(db, sheet, ctx, "Viability goal-seek applied", gs_detail)
    db.commit()
    db.refresh(line)
    return line


@router.post(
    "/viability/{viability_id}/refresh-tp-cost",
    response_model=RefreshTpCostResponse,
)
def refresh_tp_cost(
    viability_id: int,
    body: RefreshTpCostRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Re-pull TPWGST for every line under a viability sheet based on the
    chosen sourcing mode (Selected Datewise / Quot Approval Dated).

    Edit permission is sufficient — this is a tuning action, not an
    approval. Approved sheets are locked.
    """
    require_permission(MENU, "CanEdit", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)
    if sheet.status == "Approved":
        raise HTTPException(400, "Cannot refresh TP-Cost on an approved viability.")

    try:
        summary = refresh_sheet_tp_cost(
            db,
            sheet,
            mode=body.mode,
            as_of_date=body.asOfDate,
            overwrite_all=body.overwriteAll,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    sheet.lastupdateby = ctx.user_id
    sheet.lastupdateon = now_ist()
    db.commit()
    db.refresh(sheet)
    return {
        **summary,
        "sheet": sheet,
    }


@router.put("/viability/{viability_id}/approve", response_model=ViabilitySheetResponse)
def approve_viability(
    viability_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    # Resolve sheet → quotId first so failure logging has somewhere to land.
    sheet_row = (
        db.query(QuotViabilitySheet)
        .filter(QuotViabilitySheet.viabilityId == viability_id,
                QuotViabilitySheet.isActive == True)
        .first()
    )
    quot_id_for_log = sheet_row.quotId if sheet_row else 0
    try:
        # Per-stage approval gate. Phase-1 added ``CanApproveViability`` as
        # a granular flag distinct from quotation-level ``CanApprove``;
        # this endpoint historically still consulted the quotation flag,
        # which collapsed the segregation of duties the granular flag was
        # introduced for. Migration ``v3w4x5y6z7a8`` backfills the new
        # flag from ``CanApprove`` for existing roles so this switch is
        # transparent on first deploy.
        require_permission(MENU, "CanApproveViability", ctx)
        sheet = _get_sheet_or_403(db, viability_id, ctx)
        if sheet.status == "Approved":
            # Soft-flow re-approval: caller already saw "Approved" — and may
            # have edited it since (the row stays editable under soft flow).
            # The D3 short-circuit inside ``write_viability_snapshot`` decides
            # whether a new snapshot is actually written (content changed)
            # or just an audit event (content identical to the latest).
            from app.services.approval_snapshot_service import write_viability_snapshot
            result = write_viability_snapshot(db, sheet, approver_user_id=ctx.user_id)
            sheet.approvedby = ctx.user_id
            sheet.approvedon = now_ist()
            sheet.lastupdateby = ctx.user_id
            sheet.lastupdateon = now_ist()
            from app.models.quotation import QuotSummary
            quotation = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
            action_label = (
                "Viability Sheet Re-Approved"
                if result.created
                else "Viability Sheet Re-Approved (no changes)"
            )
            log_action(db, quot_id=sheet.quotId, company_id=sheet.companyId,
                       action=action_label,
                       status=quotation.status if quotation else None,
                       ctx=ctx)
            db.commit()
            db.refresh(sheet)
            return sheet
        sheet.status = "Approved"
        sheet.approvedby = ctx.user_id
        sheet.approvedon = now_ist()
        sheet.lastupdateby = ctx.user_id
        sheet.lastupdateon = now_ist()

        # Soft-flow snapshot: freeze the sheet (header + all lines) into the
        # approval-snapshot table BEFORE commit. First-time approval always
        # writes a new snapshot (no prior to compare against), so we don't
        # need to branch on ``result.created`` here.
        from app.services.approval_snapshot_service import write_viability_snapshot
        write_viability_snapshot(db, sheet, approver_user_id=ctx.user_id)

        # Phase 1: per-stage statuses are the source of truth for the
        # lifecycle position. ``QuotViabilitySheet.status`` flips to
        # 'Approved' here; the parent quotation stays at 'Converted'.
        from app.models.quotation import QuotSummary
        quotation = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
        log_action(db, quot_id=sheet.quotId, company_id=sheet.companyId,
                   action="Viability Sheet Approved",
                   status=quotation.status if quotation else None,
                   ctx=ctx)

        db.commit()
        db.refresh(sheet)
        return sheet
    except Exception as e:
        if quot_id_for_log:
            log_failure(db, quot_id=quot_id_for_log, company_id=ctx.company_id,
                        action="Approve Viability", user_id=ctx.user_id, exc=e)
        raise


@router.get("/viability/{viability_id}/export")
def export_viability_xlsx(
    viability_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Returns a two-sheet XLSX (Working Sheet + Viability Sheet)."""
    require_permission(MENU, "CanRead", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)

    # Delayed import so the openpyxl-heavy module is only loaded on export.
    from app.services.viability_excel_service import build_viability_xlsx

    working = _load_working_sheet(db, sheet.quotId)
    lines = sorted([l for l in sheet.lines if l.isActive], key=lambda x: x.viabilityLineId)

    quot = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
    xlsx_bytes = build_viability_xlsx(
        quot=quot,
        working_sheet=working,
        viability_lines=lines,
    )
    filename = f"ViabilitySheet-{quot.quotNo or sheet.quotId}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ---------------------------------------------------------------------------
# Soft-flow approval snapshots (SF6)
# ---------------------------------------------------------------------------
# When the head sheet is editable post-approval, callers need a way to fetch
# the *frozen* version that was signed off. ``write_viability_snapshot``
# captures one row per Approve action; these endpoints surface them. Two
# shapes: a metadata-only list for the history dropdown, and a detail
# endpoint that includes the parsed JSON body for the "view as approved"
# toggle.

@router.get(
    "/viability/{viability_id}/approval-snapshots",
    response_model=ViabilityApprovalSnapshotList,
)
def list_viability_snapshots(
    viability_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """List every approval snapshot for this quotation newest first.

    Phase B fix v2 (2026-05-21): the prior cycle-JOIN scoping excluded
    sister sheets whose ``quotOrderCycleId`` happened to be NULL,
    causing the Re-generate dialog to fall back to head-only mode and
    misclassify the picked sheet id as a snapshot id (→ "Viability
    snapshot 32 not found" 404). Quotation-wide scoping is simpler,
    surfaces every approval ever signed off on the quotation, and
    avoids the cycle-data edge case entirely.

    Snapshots are append-only (model docstring) so no isActive filter
    is needed here either — every row is valid history.
    """
    require_permission(MENU, "CanRead", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)
    snaps = (
        db.query(QuotViabilityApprovalSnapshot)
        .filter(QuotViabilityApprovalSnapshot.quotId == sheet.quotId)
        .order_by(QuotViabilityApprovalSnapshot.snapshotId.desc())
        .all()
    )
    return ViabilityApprovalSnapshotList(items=[
        ViabilityApprovalSnapshotSummary.model_validate(s) for s in snaps
    ])


@router.get(
    "/viability/{viability_id}/approval-snapshots/latest",
    response_model=ViabilityApprovalSnapshotDetail,
)
def get_latest_viability_snapshot(
    viability_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Return the most recently captured approval snapshot for this
    quotation, body included. 404 when none has ever been approved.

    Phase B fix v2: quotation-wide scope (see list_viability_snapshots)."""
    import json
    require_permission(MENU, "CanRead", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)

    snap = (
        db.query(QuotViabilityApprovalSnapshot)
        .filter(QuotViabilityApprovalSnapshot.quotId == sheet.quotId)
        .order_by(QuotViabilityApprovalSnapshot.snapshotId.desc())
        .first()
    )
    if snap is None:
        raise HTTPException(404, "No approval snapshot for this viability sheet yet.")
    body = json.loads(snap.snapshotData)
    return ViabilityApprovalSnapshotDetail(
        snapshotId=snap.snapshotId,
        viabilityId=snap.viabilityId,
        quotId=snap.quotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        snapshot=body,
    )


@router.get(
    "/viability/{viability_id}/approval-snapshots/{snapshot_id}",
    response_model=ViabilityApprovalSnapshotDetail,
)
def get_viability_snapshot_by_id(
    viability_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Fetch a specific historical snapshot by id. Scoped to the
    quotation so cross-quotation snapshot ids can't leak."""
    import json
    require_permission(MENU, "CanRead", ctx)
    sheet = _get_sheet_or_403(db, viability_id, ctx)
    snap = (
        db.query(QuotViabilityApprovalSnapshot)
        .filter(
            QuotViabilityApprovalSnapshot.snapshotId == snapshot_id,
            QuotViabilityApprovalSnapshot.quotId == sheet.quotId,
        )
        .first()
    )
    if snap is None:
        raise HTTPException(404, "Snapshot not found for this viability sheet.")
    body = json.loads(snap.snapshotData)
    return ViabilityApprovalSnapshotDetail(
        snapshotId=snap.snapshotId,
        viabilityId=snap.viabilityId,
        quotId=snap.quotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        snapshot=body,
    )


# ---------------------------------------------------------------------------
# Soft-flow version-switch (load a snapshot into the live editor)
# ---------------------------------------------------------------------------
# Mirror of the FWS restore endpoint. Loads a frozen viability snapshot
# back into the live sheet + lines so the user can edit forward from
# that point. The next Approve creates a new snapshot version (or fires
# the D3 short-circuit if unchanged).

@router.post(
    "/viability/{viability_id}/approval-snapshots/{snapshot_id}/load",
)
def load_viability_snapshot(
    viability_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Restore a viability snapshot — the snapshot's content replaces
    the sheet's current header + line rows. User edits forward from
    there; the next Approve creates a forked version.

    Permission: ``CanEdit`` is enough (restore is structurally an edit,
    not a privileged action). Audit log records the source version so
    the trail "v5 forked from v2 via switch" stays visible.
    """
    from app.services.approval_snapshot_service import (
        restore_viability_from_snapshot,
    )
    try:
        require_permission(MENU, "CanEdit", ctx)
        sheet = _get_sheet_or_403(db, viability_id, ctx)
        # Quotation-wide lookup so loading a snapshot from a prior
        # sheet (pre-Re-generate) still works. The restore writes the
        # picked snapshot's blob into the *current* sheet — picking V2
        # from an archived predecessor brings its data forward into
        # today's working draft.
        snap = (
            db.query(QuotViabilityApprovalSnapshot)
            .filter(
                QuotViabilityApprovalSnapshot.snapshotId == snapshot_id,
                QuotViabilityApprovalSnapshot.quotId == sheet.quotId,
            )
            .first()
        )
        if snap is None:
            raise HTTPException(404, "Snapshot not found for this viability sheet.")
        try:
            line_count = restore_viability_from_snapshot(
                db, sheet, snap, user_id=ctx.user_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        label = f"V{snap.versionNo}"
        log_action(
            db, quot_id=sheet.quotId, company_id=sheet.companyId,
            action="Viability Restored from snapshot",
            status=sheet.status, ctx=ctx,
            details=f"viability #{sheet.viabilityId} · restored {label} · {line_count} line(s) inserted",
        )
        db.commit()
        return {
            "restoredFromSnapshotId": snap.snapshotId,
            "restoredFromLabel": label,
            "linesInserted": line_count,
        }
    except Exception as e:
        log_failure(
            db, quot_id=0, company_id=ctx.company_id,
            action="Viability Restore", ctx=ctx, exc=e,
        )
        raise
