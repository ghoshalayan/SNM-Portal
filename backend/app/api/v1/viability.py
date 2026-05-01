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
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.timezone import now_ist
from app.models.quotation import QuotDetails, QuotSummary
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.schemas.quot_viability import (
    ADJUSTABLE_HEADS,
    GoalSeekRequest,
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
    if sheet.status == "Approved":
        raise HTTPException(400, "Viability sheet is Approved and locked for edits.")


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
        status=sheet.status,
        approvedby=sheet.approvedby,
        approvedon=sheet.approvedon,
        isActive=sheet.isActive,
        lines=[
            ViabilityLineResponse.model_validate(line)
            for line in sorted(sheet.lines, key=lambda x: x.viabilityLineId)
            if line.isActive
        ],
    )
    return ViabilityBundleResponse(
        workingSheet=_load_working_sheet(db, sheet.quotId),
        viability=sheet_resp,
    )


# ------------------------------------------------------------------ endpoints
@router.post("/quotations/{quot_id}/viability", response_model=ViabilityBundleResponse)
def create_viability(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Generate the viability sheet for a Matured quotation. Idempotent —
    returns the existing sheet if one is already present.
    """
    try:
        require_permission(MENU, "CanEdit", ctx)
        quotation = _get_quotation_or_403(db, quot_id, ctx)
        try:
            sheet = generate_viability_sheet(db, quotation=quotation, user_id=ctx.user_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

        # Propagate quotation status: Matured → ViabilityGenerated on first generate
        if quotation.status == "Matured":
            from app.core.timezone import now_ist
            quotation.status = "ViabilityGenerated"
            quotation.lastupdateby = ctx.user_id
            quotation.lastupdateon = now_ist()
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
               user_id=ctx.user_id,
               details=detail)
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
    log_action(db, quot_id=sheet.quotId, company_id=sheet.companyId,
               action="Viability goal-seek applied",
               status=quotation.status if quotation else None,
               user_id=ctx.user_id,
               details=f"lineId={line_id} · target={body.target} · "
                       f"heads: {', '.join(body.adjustableHeads)}")
    db.commit()
    db.refresh(line)
    return line


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
        require_permission(MENU, "CanApprove", ctx)
        sheet = _get_sheet_or_403(db, viability_id, ctx)
        if sheet.status == "Approved":
            return sheet
        sheet.status = "Approved"
        sheet.approvedby = ctx.user_id
        sheet.approvedon = now_ist()
        sheet.lastupdateby = ctx.user_id
        sheet.lastupdateon = now_ist()

        # Propagate quotation status: ViabilityGenerated → ViabilityApproved
        # (also handle the case where a sheet was generated before the status
        # propagation was in place and the quotation is still at 'Matured')
        from app.models.quotation import QuotSummary
        quotation = db.query(QuotSummary).filter(QuotSummary.quotId == sheet.quotId).first()
        if quotation and quotation.status in ("Matured", "ViabilityGenerated"):
            quotation.status = "ViabilityApproved"
            quotation.lastupdateby = ctx.user_id
            quotation.lastupdateon = now_ist()
        log_action(db, quot_id=sheet.quotId, company_id=sheet.companyId,
                   action="Viability Sheet Approved",
                   status=quotation.status if quotation else None,
                   user_id=ctx.user_id)

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
