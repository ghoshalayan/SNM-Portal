"""Cycle-scoped endpoints (LOI / Multi-PO CR — Phase 1C).

Routes:
  GET   /quotations/{qid}/cycles                            → list cycles
  POST  /quotations/{qid}/cycles                            → start new cycle
  GET   /quotations/{qid}/cycles/{cId}/bundle               → one-shot workspace
  POST  /quotations/{qid}/cycles/{cId}/close                → Active → Complete
  POST  /quotations/{qid}/cycles/{cId}/abandon              → Active → Abandoned
  POST  /quotations/{qid}/cycles/{cId}/purchase-orders      → append PO / LOI

Quotation access (F2/F5/F6) tunnels through ``_get_quot_or_403`` from
the quotations router — anyone who can view the parent quotation can
view its cycles. Mutations layer the new per-stage permissions on top:
``CanStartNewCycle`` for cycle lifecycle; ``CanCaptureLOI`` /
``CanSubmitPO`` for the append-PO endpoint (picked by ``isLOI``).
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models.quot_annexure import QuotAnnexure
from app.models.quot_order_cycle import QuotOrderCycle
from app.models.approval_snapshot import QuotFWSApprovalSnapshot
from app.models.quot_po_working_sheet import QuotPOWorkingSheet
from app.models.quot_viability import QuotViabilitySheet
from app.schemas.approval_snapshot import (
    FWSApprovalSnapshotDetail,
    FWSApprovalSnapshotList,
    FWSApprovalSnapshotSummary,
)
from app.schemas.quot_order_cycle import (
    AppendPurchaseOrderRequest,
    CycleBundleResponse,
    CycleCloseRequest,
    CycleHistoryResponse,
    CycleListResponse,
    CycleResponse,
    CycleStartRequest,
    InheritancePreviewResponse,
)
from app.schemas.quot_po_working_sheet import QuotPOWorkingSheetLineResponse
from app.schemas.quot_purchase_order import QuotPurchaseOrderResponse
from app.services import approval_snapshot_service
from app.services import po_working_sheet_service, purchase_order_service
from app.services.access_service import (
    AccessContext,
    get_access_context,
    require_permission,
)
from app.services.activity_log_service import log_action, log_failure
from app.services.cycle_log_events import (
    CYCLE_ABANDONED,
    CYCLE_CLOSED,
    CYCLE_STARTED,
    LOI_APPENDED_TO_CYCLE,
    PO_APPENDED_TO_CYCLE,
)
from app.services.cycle_service import (
    CycleValidationError,
    abandon_cycle,
    close_cycle,
    get_inheritance_source,
    start_new_cycle,
)

MENU = "Quotations"

router = APIRouter()


# ------------------------------------------------------------------ helpers
def _get_quotation_or_403(db: Session, quot_id: int, ctx: AccessContext):
    """Delegate to the quotations router's access check so F2/F5/F6
    stay in one place. Delayed import dodges the module-level cycle."""
    from app.api.v1.quotations import _get_quot_or_403  # noqa: WPS433
    return _get_quot_or_403(db, quot_id, ctx)


def _get_cycle_or_404(
    db: Session, quot_id: int, cycle_id: int, include_inactive: bool = False,
) -> QuotOrderCycle:
    q = db.query(QuotOrderCycle).filter(
        QuotOrderCycle.quotOrderCycleId == cycle_id,
        QuotOrderCycle.quotId == quot_id,
    )
    if not include_inactive:
        q = q.filter(QuotOrderCycle.isActive == True)  # noqa: E712
    cycle = q.first()
    if cycle is None:
        raise HTTPException(404, "Cycle not found on this quotation.")
    return cycle


def _build_bundle(db: Session, cycle: QuotOrderCycle) -> CycleBundleResponse:
    """Stitch the per-cycle workspace shape. One PO+LOI list (full),
    plus *lite* references to the cycle's working-sheet line count and
    the head viability/annexure ids+statuses. The frontend fetches the
    full sheets on demand through their existing endpoints."""
    pos = purchase_order_service.list_purchase_orders_in_cycle(db, cycle)

    ws_count = (
        db.query(QuotPOWorkingSheet.poWorkingSheetId)
        .filter(
            QuotPOWorkingSheet.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .count()
    )

    viab = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotViabilitySheet.isActive == True,  # noqa: E712
        )
        .order_by(QuotViabilitySheet.versionNo.desc())
        .first()
    )
    annx = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotAnnexure.isActive == True,  # noqa: E712
        )
        .order_by(QuotAnnexure.versionNo.desc())
        .first()
    )

    return CycleBundleResponse(
        cycle=CycleResponse.model_validate(cycle),
        purchaseOrders=[QuotPurchaseOrderResponse.model_validate(p) for p in pos],
        workingSheetLineCount=ws_count,
        viabilityId=viab.viabilityId if viab else None,
        viabilityStatus=viab.status if viab else None,
        annexureId=annx.annexureId if annx else None,
        annexureStatus=annx.status if annx else None,
    )


# ------------------------------------------------------------------ endpoints
@router.get(
    "/quotations/{quot_id}/cycles",
    response_model=CycleListResponse,
)
def list_cycles(
    quot_id: int,
    include_abandoned: bool = False,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Every cycle on a quotation, ordered by ``cycleNo``. Abandoned
    cycles are filtered out by default — the frontend renders the
    selector strip from this and abandoned pills only appear when the
    user explicitly toggles "show abandoned"."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)

    q = db.query(QuotOrderCycle).filter(
        QuotOrderCycle.quotId == quot_id,
        QuotOrderCycle.isActive == True,  # noqa: E712
    )
    if not include_abandoned:
        q = q.filter(QuotOrderCycle.status != "Abandoned")
    cycles = q.order_by(QuotOrderCycle.cycleNo.asc()).all()
    return CycleListResponse(
        cycles=[CycleResponse.model_validate(c) for c in cycles],
    )


@router.post(
    "/quotations/{quot_id}/cycles",
    response_model=CycleResponse,
    status_code=201,
)
def start_cycle(
    quot_id: int,
    body: CycleStartRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Open a new cycle (call-off) on an Approved or Converted
    quotation. Gated by ``CanStartNewCycle``. The first cycle's
    side-effect of flipping the quotation Approved → Converted lives
    in ``cycle_service.start_new_cycle``."""
    try:
        require_permission(MENU, "CanStartNewCycle", ctx)
        quot = _get_quotation_or_403(db, quot_id, ctx)
        try:
            cycle = start_new_cycle(
                db, quot,
                started_by=ctx.user_id,
                parent_cycle_id=body.parentCycleId,
            )
        except CycleValidationError as exc:
            raise HTTPException(400, str(exc))

        if body.notes:
            cycle.notes = body.notes

        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action=CYCLE_STARTED, status=quot.status, user_id=ctx.user_id,
            details=f"cycle #{cycle.cycleNo} (id={cycle.quotOrderCycleId})",
        )
        db.commit()
        db.refresh(cycle)
        return CycleResponse.model_validate(cycle)
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="Cycle Start", user_id=ctx.user_id, exc=e,
        )
        raise


@router.get(
    "/quotations/{quot_id}/cycles/{cycle_id}/bundle",
    response_model=CycleBundleResponse,
)
def get_cycle_bundle(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """One-shot fetch for the per-cycle workspace: cycle envelope + all
    POs/LOIs in it + lite refs to WS/viability/annexure. Saves the UI
    three round-trips on each cycle-pill click."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)
    return _build_bundle(db, cycle)


@router.post(
    "/quotations/{quot_id}/cycles/{cycle_id}/close",
    response_model=CycleResponse,
)
def close_cycle_endpoint(
    quot_id: int,
    cycle_id: int,
    body: CycleCloseRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Mark a cycle Complete. Requires an approved annexure AND at
    least one formal (non-LOI) PO in the cycle — the service raises
    ``CycleValidationError`` otherwise and we map that to 400 with the
    list of unmet preconditions joined."""
    try:
        require_permission(MENU, "CanStartNewCycle", ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)
        try:
            close_cycle(db, cycle, user_id=ctx.user_id, reason=body.reason)
        except CycleValidationError as exc:
            raise HTTPException(400, str(exc))
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action=CYCLE_CLOSED, status="Complete", user_id=ctx.user_id,
            details=f"cycle #{cycle.cycleNo}" + (f" · {body.reason}" if body.reason else ""),
        )
        db.commit()
        db.refresh(cycle)
        return CycleResponse.model_validate(cycle)
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="Cycle Close", user_id=ctx.user_id, exc=e,
        )
        raise


@router.post(
    "/quotations/{quot_id}/cycles/{cycle_id}/abandon",
    response_model=CycleResponse,
)
def abandon_cycle_endpoint(
    quot_id: int,
    cycle_id: int,
    body: CycleCloseRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Mark a cycle Abandoned. Permanent — no Active → Abandoned →
    Active recovery, the escape hatch is Unlock & Edit (Phase 1F)."""
    try:
        require_permission(MENU, "CanStartNewCycle", ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)
        try:
            abandon_cycle(db, cycle, user_id=ctx.user_id, reason=body.reason)
        except CycleValidationError as exc:
            raise HTTPException(400, str(exc))
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action=CYCLE_ABANDONED, status="Abandoned", user_id=ctx.user_id,
            details=f"cycle #{cycle.cycleNo}" + (f" · {body.reason}" if body.reason else ""),
        )
        db.commit()
        db.refresh(cycle)
        return CycleResponse.model_validate(cycle)
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="Cycle Abandon", user_id=ctx.user_id, exc=e,
        )
        raise


@router.post(
    "/quotations/{quot_id}/cycles/{cycle_id}/purchase-orders",
    response_model=QuotPurchaseOrderResponse,
    status_code=201,
)
def append_purchase_order(
    quot_id: int,
    cycle_id: int,
    body: AppendPurchaseOrderRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Append a fresh PO or LOI to an Active cycle. Append-only per
    CR decision C3 — no in-place upgrades; once an LOI is captured the
    follow-up formal PO comes in as a new row with the next sequence.

    Permission is picked by ``isLOI``: ``CanCaptureLOI`` for non-binding
    intents (looser gate, KRO-and-above), ``CanSubmitPO`` for formal
    POs (stricter — already exists on the menu since Phase 1).
    """
    try:
        required_flag = "CanCaptureLOI" if body.isLOI else "CanSubmitPO"
        require_permission(MENU, required_flag, ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)
        try:
            po = purchase_order_service.append_purchase_order_to_cycle(
                db, cycle, body.to_po_body(),
                user_id=ctx.user_id, is_loi=body.isLOI,
            )
        except purchase_order_service.PurchaseOrderConflictError as exc:
            raise HTTPException(409, str(exc))
        except purchase_order_service.PurchaseOrderValidationError as exc:
            raise HTTPException(400, str(exc))

        kind = "LOI" if body.isLOI else "PO"
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action=LOI_APPENDED_TO_CYCLE if body.isLOI else PO_APPENDED_TO_CYCLE,
            status="Active", user_id=ctx.user_id,
            details=(
                f"cycle #{cycle.cycleNo} · {kind} {po.poNo} "
                f"(seq {po.loiSequence})"
            ),
        )
        db.commit()
        db.refresh(po)
        return QuotPurchaseOrderResponse.model_validate(po)
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="Cycle Append PO", user_id=ctx.user_id, exc=e,
        )
        raise


class RegenerateFwsBody(BaseModel):
    """Source pick for FWS Re-generate. Exactly one of the three
    fields must be set:

    * ``sourcedFromSnapshotId`` — restore a past FWS approval snapshot
      in this cycle's chain.
    * ``fromQuotation`` — re-clone fresh from the quotation's current
      ``QuotDetails`` rows.
    * ``parentCycleId`` — clone forward from the parent cycle's live
      FWS (only meaningful for Cycle 2+).
    """
    sourcedFromSnapshotId: int | None = None
    fromQuotation: bool = False
    parentCycleId: int | None = None


@router.post(
    "/quotations/{quot_id}/cycles/{cycle_id}/fws/regenerate",
)
def regenerate_fws_endpoint(
    quot_id: int,
    cycle_id: int,
    body: RegenerateFwsBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Replace the cycle's active FWS rows with rows sourced from
    snapshot / quotation / parent cycle. Mirrors the Viability
    Re-generate UX — user picks a source, backend rewrites the live
    working sheet, user edits + clicks Approve next.

    Returns ``{ inserted: N }`` so the FE knows how many rows were
    written.
    """
    from app.models.approval_snapshot import QuotFWSApprovalSnapshot
    from app.models.quot_order_cycle import QuotOrderCycle
    from app.services import po_working_sheet_service
    try:
        # CanRegenerateFWS is the dedicated gate; legacy roles fall
        # back to CanEdit until granted the new flag explicitly.
        if not ctx.has_permission(MENU, "CanRegenerateFWS"):
            require_permission(MENU, "CanEdit", ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)

        # Pick the cycle's anchor PO/LOI for the new rows' FK (every
        # working-sheet row has to attribute to a row in QuotPurchaseOrder
        # since quotPOId is NOT NULL). Prefer the formal PO; fall back
        # to the first active row.
        from app.models.quot_purchase_order import QuotPurchaseOrder
        cycle_pos = (
            db.query(QuotPurchaseOrder)
            .filter(
                QuotPurchaseOrder.quotOrderCycleId == cycle.quotOrderCycleId,
                QuotPurchaseOrder.isActive == True,  # noqa: E712
            )
            .order_by(QuotPurchaseOrder.quotPOId.asc())
            .all()
        )
        if not cycle_pos:
            raise HTTPException(
                400,
                "Cycle has no PO or LOI. Append one before re-generating the FWS.",
            )
        owning_po = next((p for p in cycle_pos if not p.isLOI), cycle_pos[0])

        snapshot = None
        if body.sourcedFromSnapshotId is not None:
            snapshot = (
                db.query(QuotFWSApprovalSnapshot)
                .filter(
                    QuotFWSApprovalSnapshot.snapshotId == body.sourcedFromSnapshotId,
                    QuotFWSApprovalSnapshot.quotOrderCycleId == cycle.quotOrderCycleId,
                )
                .first()
            )
            if snapshot is None:
                raise HTTPException(
                    404,
                    f"FWS snapshot {body.sourcedFromSnapshotId} not found for this cycle.",
                )

        parent_cycle = None
        if body.parentCycleId is not None:
            parent_cycle = (
                db.query(QuotOrderCycle)
                .filter(
                    QuotOrderCycle.quotOrderCycleId == body.parentCycleId,
                    QuotOrderCycle.quotId == quot_id,
                )
                .first()
            )
            if parent_cycle is None:
                raise HTTPException(
                    404,
                    f"Parent cycle {body.parentCycleId} not found for this quotation.",
                )

        try:
            inserted = po_working_sheet_service.regenerate_fws(
                db, cycle, user_id=ctx.user_id,
                owning_po=owning_po,
                snapshot=snapshot,
                re_clone_from_quotation=body.fromQuotation,
                parent_cycle=parent_cycle,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        # Audit detail tagged with which source path ran.
        if snapshot is not None:
            src_detail = (
                f"from FWS snapshot C{cycle.cycleNo}-V{snapshot.versionNo} "
                f"(snap={snapshot.snapshotId})"
            )
        elif body.fromQuotation:
            src_detail = "fresh from QuotDetails"
        else:
            src_detail = f"from parent cycle id={body.parentCycleId}"
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action="FWS Re-generated", status="Active", ctx=ctx,
            details=f"cycle #{cycle.cycleNo} · {src_detail} · {inserted} row(s)",
        )
        db.commit()
        return {"inserted": inserted}
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="FWS Re-generate", ctx=ctx, exc=e,
        )
        raise


@router.post(
    "/quotations/{quot_id}/cycles/{cycle_id}/fws/approve",
)
def approve_cycle_fws(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Approve the cycle's Final Working Sheet.

    Soft-flow design: each Approve click creates a new versioned
    snapshot of the FWS state (via ``approve_fws``). When the current
    state is identical to the latest snapshot (D3 short-circuit), no
    new version is created — we record a "re-approval (no changes)"
    audit event instead.

    Returns ``{ snapshotId, versionNo, created, label }`` where
    ``label`` is the ``C{cycleNo}-V{versionNo}`` display string the FE
    uses across the version dropdown / status chip.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        # CanApproveFWS is the dedicated gate; legacy roles fall back
        # to the broader CanApprove until granted the new flag.
        if not ctx.has_permission(MENU, "CanApproveFWS"):
            require_permission(MENU, "CanApprove", ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)
        try:
            result = approval_snapshot_service.approve_fws(
                db, cycle, approver_user_id=ctx.user_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except IntegrityError:
            # Concurrent approve race — the unique on
            # (quotOrderCycleId, versionNo) caught a duplicate. The
            # surfacing rollback is handled by the global exception
            # path; we just convert the error code so the FE can show
            # a retry-style toast instead of a generic 500.
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    "Another Approve completed concurrently. "
                    "Refresh and try again — your changes weren't lost."
                ),
            )

        label = f"C{cycle.cycleNo}-V{result.snapshot.versionNo}"
        if result.created:
            action = "FWS Approved"
            details = f"cycle #{cycle.cycleNo} · new version {label}"
        else:
            action = "FWS Re-Approved (no changes)"
            details = (
                f"cycle #{cycle.cycleNo} · content unchanged since {label}; "
                f"no new version created (D3 policy)"
            )
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action=action, status="Active",
            ctx=ctx, details=details,
        )
        db.commit()
        db.refresh(result.snapshot)
        return {
            "snapshotId": result.snapshot.snapshotId,
            "versionNo": result.snapshot.versionNo,
            "created": result.created,
            "label": label,
            "approvedAt": result.snapshot.approvedAt,
            "approvedByUserId": result.snapshot.approvedByUserId,
            "approvedByName": result.snapshot.approvedByName,
        }
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="FWS Approve", ctx=ctx, exc=e,
        )
        raise


def _snap_to_summary(
    snap: QuotFWSApprovalSnapshot, cycle_no: int,
) -> FWSApprovalSnapshotSummary:
    """Map an FWS snapshot row → summary response. Pre-computes the
    ``C{cycleNo}-V{versionNo}`` label so the FE doesn't have to know
    cycle metadata for each row."""
    return FWSApprovalSnapshotSummary(
        snapshotId=snap.snapshotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        quotOrderCycleId=snap.quotOrderCycleId,
        quotId=snap.quotId,
        label=f"C{cycle_no}-V{snap.versionNo}",
    )


@router.get(
    "/quotations/{quot_id}/cycles/{cycle_id}/fws/approval-snapshots",
    response_model=FWSApprovalSnapshotList,
)
def list_fws_snapshots(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Every FWS approval snapshot for this cycle, newest first.
    Backs the version-picker dropdown — header-only, no body."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)
    snaps = (
        db.query(QuotFWSApprovalSnapshot)
        .filter(
            QuotFWSApprovalSnapshot.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotFWSApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .order_by(QuotFWSApprovalSnapshot.snapshotId.desc())
        .all()
    )
    return FWSApprovalSnapshotList(items=[
        _snap_to_summary(s, cycle.cycleNo) for s in snaps
    ])


@router.get(
    "/quotations/{quot_id}/cycles/{cycle_id}/fws/approval-snapshots/latest",
    response_model=FWSApprovalSnapshotDetail,
)
def get_latest_fws_snapshot(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Most recent FWS snapshot, body included. 404 if the cycle's FWS
    has never been approved."""
    import json
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)
    snap = (
        db.query(QuotFWSApprovalSnapshot)
        .filter(
            QuotFWSApprovalSnapshot.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotFWSApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .order_by(QuotFWSApprovalSnapshot.snapshotId.desc())
        .first()
    )
    if snap is None:
        raise HTTPException(404, "No FWS approval snapshot for this cycle yet.")
    return FWSApprovalSnapshotDetail(
        snapshotId=snap.snapshotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        quotOrderCycleId=snap.quotOrderCycleId,
        quotId=snap.quotId,
        label=f"C{cycle.cycleNo}-V{snap.versionNo}",
        contentHash=snap.contentHash,
        snapshot=json.loads(snap.snapshotData),
    )


@router.get(
    "/quotations/{quot_id}/cycles/{cycle_id}/fws/approval-snapshots/{snapshot_id}",
    response_model=FWSApprovalSnapshotDetail,
)
def get_fws_snapshot_by_id(
    quot_id: int,
    cycle_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Fetch a specific historical FWS snapshot — required so the
    version dropdown can render any past version, not just the latest."""
    import json
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)
    snap = (
        db.query(QuotFWSApprovalSnapshot)
        .filter(
            QuotFWSApprovalSnapshot.snapshotId == snapshot_id,
            QuotFWSApprovalSnapshot.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotFWSApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .first()
    )
    if snap is None:
        raise HTTPException(404, "FWS snapshot not found for this cycle.")
    return FWSApprovalSnapshotDetail(
        snapshotId=snap.snapshotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        quotOrderCycleId=snap.quotOrderCycleId,
        quotId=snap.quotId,
        label=f"C{cycle.cycleNo}-V{snap.versionNo}",
        contentHash=snap.contentHash,
        snapshot=json.loads(snap.snapshotData),
    )


@router.post(
    "/quotations/{quot_id}/cycles/{cycle_id}/fws/approval-snapshots/{snapshot_id}/restore",
)
def restore_fws_snapshot(
    quot_id: int,
    cycle_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Restore an FWS snapshot — the snapshot's data replaces the
    cycle's current active FWS rows. Subsequent edits proceed from the
    restored state; a later Approve creates a new version forked from
    this base.

    Permission: ``CanEdit`` is enough — restore is structurally an
    edit, not a separate privileged action. Audit log records the
    restore so the trail "v5 forked from v2 via restore" is visible.
    """
    try:
        require_permission(MENU, "CanEdit", ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)
        snap = (
            db.query(QuotFWSApprovalSnapshot)
            .filter(
                QuotFWSApprovalSnapshot.snapshotId == snapshot_id,
                QuotFWSApprovalSnapshot.quotOrderCycleId == cycle.quotOrderCycleId,
                QuotFWSApprovalSnapshot.isActive == True,  # noqa: E712
            )
            .first()
        )
        if snap is None:
            raise HTTPException(404, "Snapshot not found for this cycle.")
        try:
            count = approval_snapshot_service.restore_fws_from_snapshot(
                db, cycle, snap, user_id=ctx.user_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        label = f"C{cycle.cycleNo}-V{snap.versionNo}"
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action="FWS Restored from snapshot",
            status="Active", ctx=ctx,
            details=f"cycle #{cycle.cycleNo} · restored {label} · {count} line(s) inserted",
        )
        db.commit()
        return {
            "restoredFromSnapshotId": snap.snapshotId,
            "restoredFromLabel": label,
            "rowsInserted": count,
        }
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="FWS Restore", ctx=ctx, exc=e,
        )
        raise


@router.put(
    "/quotations/{quot_id}/cycles/{cycle_id}/purchase-orders/{po_id}/submit",
)
def submit_cycle_purchase_order(
    quot_id: int,
    cycle_id: int,
    po_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Removed under the soft-flow redesign (Slice C, 2026-05-20).

    See the legacy ``/purchase-order/submit`` endpoint for rationale.
    Use the FWS Approve workflow on the cycle instead.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "PO Submit & Mature is no longer required. Use "
            "POST /quotations/{quotId}/cycles/{cycleId}/fws/approve."
        ),
    )


@router.put(
    "/quotations/{quot_id}/cycles/{cycle_id}/purchase-orders/{po_id}/reject",
)
def reject_cycle_purchase_order(
    quot_id: int,
    cycle_id: int,
    po_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Removed under the soft-flow redesign (Slice C, 2026-05-20).

    Use ``DELETE /cycles/{cycleId}/purchase-orders/{poId}`` to withdraw
    a specific PO, or ``POST /cycles/{cycleId}/abandon`` to roll the
    whole cycle back.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "PO Reject is no longer required. Use "
            "DELETE /quotations/{quotId}/cycles/{cycleId}/purchase-orders/{poId} "
            "to withdraw a PO, or POST /cycles/{cycleId}/abandon "
            "to roll the cycle back."
        ),
    )


@router.delete(
    "/quotations/{quot_id}/cycles/{cycle_id}/purchase-orders/{po_id}",
    status_code=204,
)
def withdraw_cycle_purchase_order(
    quot_id: int,
    cycle_id: int,
    po_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Withdraw a PO (or LOI) from a cycle — replaces the retired
    Reject endpoint. Soft-deletes the row; the cycle keeps running.

    No status transitions, no cascading un-Convert on the quotation.
    The cycle close precondition (``≥1 active formal PO``) is still
    enforced at close time, so withdrawing the last formal PO simply
    blocks close until another is appended.
    """
    try:
        require_permission(MENU, "CanRejectPO", ctx)
        _get_quotation_or_403(db, quot_id, ctx)
        cycle = _get_cycle_or_404(db, quot_id, cycle_id)
        from app.models.quot_purchase_order import QuotPurchaseOrder
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
            raise HTTPException(404, "PO not found in this cycle (or already withdrawn).")
        po.isActive = False
        po.lastupdateby = ctx.user_id
        log_action(
            db, quot_id=quot_id, company_id=cycle.companyId,
            action="PO Withdrawn", status="Active", ctx=ctx,
            details=f"cycle #{cycle.cycleNo} · PO {po.poNo} (id={po.quotPOId})",
        )
        db.commit()
        return None
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action="Cycle PO Withdraw", ctx=ctx, exc=e,
        )
        raise


# ----------------------------------------------------------------------
# Phase 1E — rate inheritance preview + cycle-scoped FWS
# ----------------------------------------------------------------------

@router.get(
    "/quotations/{quot_id}/cycles/{cycle_id}/inheritance-preview",
    response_model=InheritancePreviewResponse,
)
def inheritance_preview(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Peek what the given cycle would inherit if its first PO were
    appended right now. Backs the Start New Call-off confirm dialog
    so users see "12 lines from Cycle 1's approved viability" up
    front instead of finding out post-hoc.

    Caller passes the *parent* cycle id (i.e. the cycle whose source
    the new one will pull from), not the not-yet-created child. For
    a Cycle-1 preview the parent doesn't exist yet — caller short-
    circuits client-side, but we also return ``none`` defensively
    when the cycle has no inheritable rows."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    parent_cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)
    src = get_inheritance_source(db, parent_cycle)
    return InheritancePreviewResponse(
        parentCycleId=parent_cycle.quotOrderCycleId,
        parentCycleNo=parent_cycle.cycleNo,
        sourceType=src.source_type,
        lineCount=len(src.lines),
    )


@router.get(
    "/quotations/{quot_id}/cycles/{cycle_id}/working-sheet",
    response_model=List[QuotPOWorkingSheetLineResponse],
)
def list_cycle_working_sheet(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Cycle-scoped Final Working Sheet list. One WS per cycle (CR
    decision C2) so this returns every active row attached to the
    given cycle regardless of which PO/LOI owns the FK. Replaces the
    legacy ``GET /quotations/{id}/purchase-order/working-sheet``
    single-PO path for cycle-aware clients."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)
    return po_working_sheet_service.list_working_sheet_for_cycle(db, cycle)


# ----------------------------------------------------------------------
# Phase 1F — Cycle History (read-only timeline)
# ----------------------------------------------------------------------

@router.get(
    "/quotations/{quot_id}/cycles/history",
    response_model=CycleHistoryResponse,
)
def cycle_history(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Every cycle on a quotation, each one rendered as a full bundle.
    Backs the read-only "Cycle History" tab in Stage 2 so the user can
    survey every call-off (POs, LOIs, viability, annexure refs) in one
    glance without paging through each cycle pill.

    Includes Abandoned cycles unconditionally — history is exhaustive
    by design. Ordering is by ``cycleNo`` ascending so the timeline
    reads top-to-bottom in chronological order."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)

    cycles = (
        db.query(QuotOrderCycle)
        .filter(
            QuotOrderCycle.quotId == quot_id,
            QuotOrderCycle.isActive == True,  # noqa: E712
        )
        .order_by(QuotOrderCycle.cycleNo.asc())
        .all()
    )
    return CycleHistoryResponse(
        bundles=[_build_bundle(db, c) for c in cycles],
    )


# ----------------------------------------------------------------------
# Phase 1G — cycle Excel export
# ----------------------------------------------------------------------

@router.get("/quotations/{quot_id}/cycles/{cycle_id}/export")
def export_cycle_xlsx(
    quot_id: int,
    cycle_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Three-sheet workbook (Summary + Working Sheet + Viability) for
    one cycle. The Viability sheet is omitted when the cycle has no
    approved viability — keeps the file faithful to what actually
    exists rather than padding empty tabs.

    Logged via ``CYCLE_EXPORTED_XLSX`` for the renewal-audit trail.
    """
    from app.models.quot_annexure import QuotAnnexure  # local — heavy import
    from app.services.cycle_excel_service import build_cycle_xlsx
    from app.services.cycle_log_events import CYCLE_EXPORTED_XLSX

    require_permission(MENU, "CanRead", ctx)
    quot = _get_quotation_or_403(db, quot_id, ctx)
    cycle = _get_cycle_or_404(db, quot_id, cycle_id, include_inactive=True)

    parent = None
    if cycle.parentCycleId:
        parent = (
            db.query(QuotOrderCycle)
            .filter(QuotOrderCycle.quotOrderCycleId == cycle.parentCycleId)
            .first()
        )

    pos = purchase_order_service.list_purchase_orders_in_cycle(db, cycle)
    ws_rows = po_working_sheet_service.list_working_sheet_for_cycle(db, cycle)

    viab = (
        db.query(QuotViabilitySheet)
        .filter(
            QuotViabilitySheet.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotViabilitySheet.isActive == True,  # noqa: E712
        )
        .order_by(QuotViabilitySheet.versionNo.desc())
        .first()
    )
    viab_lines = []
    if viab is not None:
        from app.models.quot_viability import QuotViabilityLine
        viab_lines = (
            db.query(QuotViabilityLine)
            .filter(
                QuotViabilityLine.viabilityId == viab.viabilityId,
                QuotViabilityLine.isActive == True,  # noqa: E712
            )
            .order_by(QuotViabilityLine.viabilityLineId.asc())
            .all()
        )

    annx = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotAnnexure.isActive == True,  # noqa: E712
        )
        .order_by(QuotAnnexure.versionNo.desc())
        .first()
    )

    xlsx_bytes = build_cycle_xlsx(
        quot=quot,
        cycle=cycle,
        parent_cycle=parent,
        purchase_orders=pos,
        working_sheet=ws_rows,
        viability=viab,
        viability_lines=viab_lines,
        annexure=annx,
    )

    log_action(
        db, quot_id=quot_id, company_id=cycle.companyId,
        action=CYCLE_EXPORTED_XLSX, status=cycle.status, user_id=ctx.user_id,
        details=f"cycle #{cycle.cycleNo}",
    )
    db.commit()

    quot_no = (quot.quotNo if quot and quot.quotNo else f"Q-{quot_id}")
    filename = f"Cycle-{cycle.cycleNo}-{quot_no}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
