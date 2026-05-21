"""Annexure endpoints.

  POST /quotations/{qid}/annexure   → generate (idempotent)
  GET  /quotations/{qid}/annexure   → fetch
  PUT  /annexure/{aid}              → full partial update (all 25 fields)
  PUT  /annexure/{aid}/approve      → HOD approval; freezes the document

Also propagates status through the QuotSummary lifecycle:
  Matured → ViabilityGenerated → ViabilityApproved → AnnexureGenerated → AnnexureApproved
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.timezone import now_ist
from app.models.approval_snapshot import QuotAnnexureApprovalSnapshot
from app.models.quot_annexure import QuotAnnexure
from app.models.quotation import QuotSummary
from app.models.user import User
from app.schemas.approval_snapshot import (
    AnnexureApprovalSnapshotDetail,
    AnnexureApprovalSnapshotList,
    AnnexureApprovalSnapshotSummary,
)
from app.schemas.quot_annexure import AnnexureResponse, AnnexureUpdate, DiaBreakupEntry
from app.services.access_service import AccessContext, get_access_context, require_permission
from app.models.quot_viability import QuotViabilitySheet
from app.services.annexure_service import (
    deserialize_breakup,
    generate_annexure,
    refill_annexure_from_viability,
    resource_annexure,
)
from app.services.activity_log_service import log_action, log_failure

MENU = "Quotations"

router = APIRouter()


def _get_quotation_or_403(db: Session, quot_id: int, ctx: AccessContext) -> QuotSummary:
    from app.api.v1.quotations import _get_quot_or_403  # noqa: WPS433
    return _get_quot_or_403(db, quot_id, ctx)


def _get_annexure_or_403(
    db: Session,
    annexure_id: int,
    ctx: AccessContext,
    *,
    for_update: bool = False,
) -> QuotAnnexure:
    """Fetch the annexure with the standard access check.

    When ``for_update=True`` (write endpoints only — never read paths)
    the row is fetched ``SELECT ... FOR UPDATE`` so concurrent mutations
    on the same annexure serialize. Required for N15: without it, an
    edit and an approve hitting the same row simultaneously can result
    in the edit landing on a row that just turned Approved.
    """
    q = db.query(QuotAnnexure).filter(
        QuotAnnexure.annexureId == annexure_id,
        QuotAnnexure.isActive == True,
    )
    if for_update:
        q = q.with_for_update()
    ann = q.first()
    if not ann:
        raise HTTPException(404, "Annexure not found")
    _get_quotation_or_403(db, ann.quotId, ctx)
    return ann


def _to_response(ann: QuotAnnexure) -> dict:
    """Convert ORM → response dict (deserializes the stored JSON breakup)."""
    data = {c.key: getattr(ann, c.key) for c in QuotAnnexure.__table__.columns}
    data["diawiseBreakup"] = deserialize_breakup(ann.diawiseBreakup)
    return data


class GenerateAnnexureBody(BaseModel):
    """Optional source-picker payload for annexure generation (Slice B).

    Both fields default to None — when omitted, the endpoint uses
    latest-active viability + ``quotation.purchase_order`` (legacy
    behaviour). When supplied, the picker wins.
    """
    sourcedFromViabilityId: int | None = None
    sourcedFromPOId: int | None = None


@router.post("/quotations/{quot_id}/annexure", response_model=AnnexureResponse)
def create_annexure(
    quot_id: int,
    body: GenerateAnnexureBody | None = None,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Generate annexure from quotation + viability. Idempotent.

    Slice B: optional body fields pin the source viability and PO.
    Omitting either retains the legacy default-selection behaviour.
    """
    try:
        require_permission(MENU, "CanEdit", ctx)
        quotation = _get_quotation_or_403(db, quot_id, ctx)
        viab_id = body.sourcedFromViabilityId if body is not None else None
        po_id = body.sourcedFromPOId if body is not None else None
        try:
            annexure = generate_annexure(
                db, quotation=quotation, user_id=ctx.user_id,
                sourced_from_viability_id=viab_id,
                sourced_from_po_id=po_id,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

        # Phase 1: per-stage statuses are the source of truth. The
        # annexure has its own ``status``='Draft' on creation; the
        # parent quotation stays at 'Converted'.
        log_action(db, quot_id=quotation.quotId, company_id=quotation.companyId,
                   action="Annexure Generated", status=quotation.status, ctx=ctx)

        db.commit()
        db.refresh(annexure)
        return _to_response(annexure)
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Generate Annexure", ctx=ctx, exc=e)
        raise


@router.get("/quotations/{quot_id}/annexure", response_model=Optional[AnnexureResponse])
def get_annexure(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Returns the annexure, or null when none has been generated yet."""
    require_permission(MENU, "CanRead", ctx)
    _get_quotation_or_403(db, quot_id, ctx)
    ann = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.quotId == quot_id,
            QuotAnnexure.isActive == True,
        )
        .first()
    )
    if not ann:
        return None
    return _to_response(ann)


@router.put("/annexure/{annexure_id}", response_model=AnnexureResponse)
def update_annexure(
    annexure_id: int,
    body: AnnexureUpdate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Partial update; any key supplied gets written. Diawise breakup
    can be re-submitted as an array (stored as JSON)."""
    require_permission(MENU, "CanEdit", ctx)
    # N15: row-lock the annexure so a concurrent ``/approve`` cannot
    # flip its status mid-flight. Without the row lock both could read
    # status='Draft' simultaneously and double-write the same column.
    ann = _get_annexure_or_403(db, annexure_id, ctx, for_update=True)
    # 2026-05-21 lifecycle rework: Approved annexures are locked.
    # Re-generate is the explicit unlock path (archives head, creates
    # a fresh Draft from a picked source).
    if ann.status == "Approved":
        raise HTTPException(
            status_code=400,
            detail=(
                "Annexure is locked — it was Approved. Click "
                "Re-generate to create a fresh editable draft."
            ),
        )
    was_approved = False

    data = body.model_dump(exclude_unset=True)
    breakup = data.pop("diawiseBreakup", None)
    if breakup is not None:
        # Accept list of DiaBreakupEntry-shaped dicts or raw pydantic objects
        clean = []
        for row in breakup:
            if isinstance(row, DiaBreakupEntry):
                clean.append(row.model_dump())
            elif isinstance(row, dict):
                clean.append({
                    "dia": row.get("dia"),
                    "qty": float(row["qty"]) if row.get("qty") is not None else None,
                    "amount": float(row["amount"]) if row.get("amount") is not None else None,
                })
        ann.diawiseBreakup = json.dumps(clean)

    changed_fields: list[str] = []
    for k, v in data.items():
        if getattr(ann, k, None) != v:
            changed_fields.append(k)
        setattr(ann, k, v)
    if breakup is not None:
        changed_fields.append("diawiseBreakup")

    ann.lastupdateby = ctx.user_id
    ann.lastupdateon = now_ist()
    if changed_fields:
        quotation = db.query(QuotSummary).filter(QuotSummary.quotId == ann.quotId).first()
        log_action(db, quot_id=ann.quotId, company_id=ann.companyId,
                   action="Annexure field updated",
                   status=quotation.status if quotation else None,
                   ctx=ctx,
                   details=f"fields: {', '.join(changed_fields)}")
        if was_approved:
            log_action(db, quot_id=ann.quotId, company_id=ann.companyId,
                       action="Annexure field updated (after approval)",
                       status=quotation.status if quotation else None,
                       ctx=ctx,
                       details=f"fields: {', '.join(changed_fields)}")
    db.commit()
    db.refresh(ann)
    return _to_response(ann)


@router.put("/annexure/{annexure_id}/approve", response_model=AnnexureResponse)
def approve_annexure(
    annexure_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Approve the annexure. Sets Checked-By and Approved-By to the approver
    (both signatures fall to HOD in the current single-approval flow)."""
    # Resolve annexure → quotId up front so a failure log has somewhere to land.
    pre_ann = (
        db.query(QuotAnnexure)
        .filter(QuotAnnexure.annexureId == annexure_id,
                QuotAnnexure.isActive == True)
        .first()
    )
    quot_id_for_log = pre_ann.quotId if pre_ann else 0
    try:
        # Annexure approval is gated specifically on CanApproveAnnexure,
        # not the generic CanApprove. This separates annexure sign-off
        # (Commercial HOD's responsibility) from quotation approval
        # (regular HOD's responsibility) — same role can hold both, but
        # only Commercial HOD has CanApproveAnnexure by default.
        require_permission(MENU, "CanApproveAnnexure", ctx)
        # N15: lock the row before we read its status. The pair
        # (read status, set Approved) is atomic only when the read
        # holds an exclusive lock through to commit.
        ann = _get_annexure_or_403(db, annexure_id, ctx, for_update=True)
        # Soft-flow re-approval: row stays editable post-approval, so
        # re-clicking Approve writes a fresh snapshot capturing whatever
        # the current state is. Don't early-return — that would
        # silently swallow the user's intent to re-sign.
        if ann.status == "Approved":
            # N16 still applies on re-approval too.
            if (
                not ctx.is_super_admin
                and ann.createdby is not None
                and ann.createdby == ctx.user_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "You cannot approve an annexure you created. "
                        "Ask another holder of the Commercial HOD role to sign it off."
                    ),
                )
            from app.services.approval_snapshot_service import write_annexure_snapshot
            result = write_annexure_snapshot(db, ann, approver_user_id=ctx.user_id)
            ann.approvedon = now_ist()
            ann.lastupdateby = ctx.user_id
            ann.lastupdateon = now_ist()
            quotation = db.query(QuotSummary).filter(QuotSummary.quotId == ann.quotId).first()
            action_label = (
                "Annexure Re-Approved"
                if result.created
                else "Annexure Re-Approved (no changes)"
            )
            log_action(db, quot_id=ann.quotId, company_id=ann.companyId,
                       action=action_label,
                       status=quotation.status if quotation else None,
                       ctx=ctx)
            db.commit()
            db.refresh(ann)
            return _to_response(ann)

        # N16: Segregation of duties — the person who created the
        # annexure cannot be the same person who signs it off. The
        # Commercial HOD role exists specifically to provide that
        # second pair of eyes; without this check the permission flag
        # alone would let a single user create-and-approve their own
        # commercial schedule. SuperAdmin bypasses (operational
        # break-glass) but the action is still recorded against them
        # in the activity log.
        if (
            not ctx.is_super_admin
            and ann.createdby is not None
            and ann.createdby == ctx.user_id
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    "You cannot approve an annexure you created. "
                    "Ask another holder of the Commercial HOD role to sign it off."
                ),
            )

        approver = db.query(User).filter(User.userId == ctx.user_id).first()
        approver_name = approver.userName if approver else None

        ann.status = "Approved"
        ann.approvedByUserId = ctx.user_id
        ann.approvedByName = approver_name
        ann.approvedon = now_ist()
        # Checked-by also falls to the approver in single-approval mode; user can
        # override on the form before approving if needed.
        if not ann.checkedByUserId:
            ann.checkedByUserId = ctx.user_id
            ann.checkedByName = approver_name
        ann.lastupdateby = ctx.user_id
        ann.lastupdateon = now_ist()

        # Soft-flow snapshot: freeze the annexure at the moment of approval
        # so future edits to the head don't lose the "what was signed off"
        # answer. Single row + JSON blob — see approval_snapshot_service.
        from app.services.approval_snapshot_service import write_annexure_snapshot
        write_annexure_snapshot(db, ann, approver_user_id=ctx.user_id)

        # Phase 1: per-stage statuses are the source of truth. The
        # annexure's ``status`` flips to 'Approved'; the parent
        # quotation stays at 'Converted'.
        quotation = db.query(QuotSummary).filter(QuotSummary.quotId == ann.quotId).first()
        log_action(db, quot_id=ann.quotId, company_id=ann.companyId,
                   action="Annexure Approved",
                   status=quotation.status if quotation else None,
                   ctx=ctx)

        db.commit()
        db.refresh(ann)
        return _to_response(ann)
    except Exception as e:
        if quot_id_for_log:
            log_failure(db, quot_id=quot_id_for_log, company_id=ctx.company_id,
                        action="Approve Annexure", ctx=ctx, exc=e)
        raise


@router.post(
    "/annexure/{annexure_id}/refill-from-viability/{viability_id}",
    response_model=AnnexureResponse,
)
def refill_annexure_breakup(
    annexure_id: int,
    viability_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Recompute the Diawise Breakup + viability-driven totals from a
    chosen viability version. User flow #4: the KRO picks a viability
    version in the annexure UI's dropdown and clicks "Refill from this
    viability" — the annexure's breakup, total qty, total amount, and
    transport-charges/MT all snap to the picked version. Header fields
    (client, addresses, payment terms) are NOT touched.

    Rejects when the annexure is already Approved (use Unlock & Edit
    first) or when the picked viability belongs to a different
    quotation. Both surface as HTTP 400 with the underlying message.
    """
    try:
        require_permission(MENU, "CanEdit", ctx)
        ann = _get_annexure_or_403(db, annexure_id, ctx)
        viability = (
            db.query(QuotViabilitySheet)
            .filter(QuotViabilitySheet.viabilityId == viability_id)
            .first()
        )
        if viability is None:
            raise HTTPException(404, "Viability version not found.")
        try:
            ann = refill_annexure_from_viability(
                db, annexure=ann, viability=viability, user_id=ctx.user_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        log_action(
            db, quot_id=ann.quotId, company_id=ann.companyId,
            action="Annexure breakup refilled",
            status=None, ctx=ctx,
            details=f"viability v{viability.versionNo} (id={viability.viabilityId})",
        )
        db.commit()
        db.refresh(ann)
        return _to_response(ann)
    except Exception as e:
        log_failure(
            db, quot_id=getattr(ann, "quotId", None) or 0,
            company_id=ctx.company_id,
            action="Refill Annexure", ctx=ctx, exc=e,
        )
        raise


# ---------------------------------------------------------------------------
# Phase C — Re-source annexure (refresh auto-populated header + diawise)
# ---------------------------------------------------------------------------
# Distinct from refill-from-viability: that one only refreshes the
# viability-derived fields. Re-source also accepts a new PO/LOI pick and
# refreshes the PO-derived header in the same call. Both refresh paths
# leave user-edited body fields (payment terms, delivery schedule,
# remarks, signatures, etc.) untouched.

class ResourceAnnexureBody(BaseModel):
    """Source picks for the Re-generate action.

    ``sourcedFromViabilityId`` is required (the sheet head FK). When
    the user picked a past **snapshot** of viability in the dialog,
    ``sourcedFromViabilitySnapshotId`` is also passed — the backend
    reads the frozen lines from the snapshot blob rather than the
    live sheet head. This keeps re-generate working even when the
    picked viability sheet has been archived by a downstream
    Re-generate. ``sourcedFromPOId`` is the PO/LOI row whose header
    feeds the annexure customer + addresses block.
    """
    sourcedFromViabilityId: int
    sourcedFromPOId: int
    sourcedFromViabilitySnapshotId: int | None = None


@router.post(
    "/annexure/{annexure_id}/resource",
    response_model=AnnexureResponse,
)
def resource_annexure_endpoint(
    annexure_id: int,
    body: ResourceAnnexureBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Re-generate an existing annexure from a different Viability
    version and/or PO/LOI. Only the auto-populated header + diawise
    are refreshed; user-edited body fields stay intact.

    Soft-flow: works on Draft AND Approved annexures. The previously
    approved snapshot stays frozen in the snapshot table; the next
    Approve creates the next version. Returns the refreshed annexure."""
    from app.models.quot_purchase_order import QuotPurchaseOrder
    from app.models.approval_snapshot import QuotViabilityApprovalSnapshot
    import logging
    log = logging.getLogger(__name__)
    log.info(
        "resource_annexure_endpoint annexure_id=%s body=%r",
        annexure_id,
        body.model_dump(),
    )
    try:
        require_permission(MENU, "CanEdit", ctx)
        ann = _get_annexure_or_403(db, annexure_id, ctx, for_update=True)
        viability = (
            db.query(QuotViabilitySheet)
            .filter(QuotViabilitySheet.viabilityId == body.sourcedFromViabilityId)
            .first()
        )
        if viability is None:
            raise HTTPException(
                404,
                f"Viability version {body.sourcedFromViabilityId} not found.",
            )
        po = (
            db.query(QuotPurchaseOrder)
            .filter(
                QuotPurchaseOrder.quotPOId == body.sourcedFromPOId,
                QuotPurchaseOrder.isActive == True,  # noqa: E712
            )
            .first()
        )
        if po is None:
            raise HTTPException(
                404,
                f"PO/LOI {body.sourcedFromPOId} not found (or inactive).",
            )
        viab_snapshot = None
        if body.sourcedFromViabilitySnapshotId is not None:
            # Snapshots are append-only by design (see the model
            # docstring) — there is no UPDATE/DELETE path. Drop the
            # isActive filter on lookup so any historical row is
            # usable as a source, even if some legacy migration nulled
            # the flag.
            viab_snapshot = (
                db.query(QuotViabilityApprovalSnapshot)
                .filter(
                    QuotViabilityApprovalSnapshot.snapshotId
                        == body.sourcedFromViabilitySnapshotId,
                )
                .first()
            )
            if viab_snapshot is None:
                # Cross-check: query without ANY filter to see if the
                # row exists at all under some weird state. The log
                # output tells the operator exactly what's in the DB
                # vs what the FE sent.
                any_row = db.execute(
                    text(
                        "SELECT snapshotId, viabilityId, versionNo, isActive "
                        "FROM QuotViabilityApprovalSnapshot WHERE snapshotId = :sid"
                    ),
                    {"sid": body.sourcedFromViabilitySnapshotId},
                ).fetchone()
                log.warning(
                    "Viability snapshot %s missing from QuotViabilityApprovalSnapshot. "
                    "Direct SELECT returned: %r",
                    body.sourcedFromViabilitySnapshotId,
                    any_row,
                )
                raise HTTPException(
                    404,
                    f"Viability snapshot {body.sourcedFromViabilitySnapshotId} not found.",
                )
        try:
            ann = resource_annexure(
                db, annexure=ann, viability=viability, po=po,
                user_id=ctx.user_id,
                viability_snapshot=viab_snapshot,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        viab_label = (
            f"v{viab_snapshot.versionNo} (snap={viab_snapshot.snapshotId})"
            if viab_snapshot is not None
            else f"v{viability.versionNo} (id={viability.viabilityId})"
        )
        log_action(
            db, quot_id=ann.quotId, company_id=ann.companyId,
            action="Annexure Re-generated", status=ann.status, ctx=ctx,
            details=(
                f"viability {viab_label} · PO {po.poNo} (id={po.quotPOId})"
            ),
        )
        db.commit()
        db.refresh(ann)
        return _to_response(ann)
    except Exception as e:
        log_failure(
            db, quot_id=getattr(ann, "quotId", None) or 0,
            company_id=ctx.company_id,
            action="Re-generate Annexure", ctx=ctx, exc=e,
        )
        raise


# ---------------------------------------------------------------------------
# Soft-flow approval snapshots (SF6) — see viability.py for the design notes.
# ---------------------------------------------------------------------------

@router.get(
    "/annexure/{annexure_id}/approval-snapshots",
    response_model=AnnexureApprovalSnapshotList,
)
def list_annexure_snapshots(
    annexure_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """List every approval snapshot for this annexure, newest first."""
    require_permission(MENU, "CanRead", ctx)
    _get_annexure_or_403(db, annexure_id, ctx)
    snaps = (
        db.query(QuotAnnexureApprovalSnapshot)
        .filter(
            QuotAnnexureApprovalSnapshot.annexureId == annexure_id,
            QuotAnnexureApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .order_by(QuotAnnexureApprovalSnapshot.snapshotId.desc())
        .all()
    )
    return AnnexureApprovalSnapshotList(items=[
        AnnexureApprovalSnapshotSummary.model_validate(s) for s in snaps
    ])


@router.get(
    "/annexure/{annexure_id}/approval-snapshots/latest",
    response_model=AnnexureApprovalSnapshotDetail,
)
def get_latest_annexure_snapshot(
    annexure_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Return the most recent approval snapshot, body included."""
    import json
    require_permission(MENU, "CanRead", ctx)
    _get_annexure_or_403(db, annexure_id, ctx)
    snap = (
        db.query(QuotAnnexureApprovalSnapshot)
        .filter(
            QuotAnnexureApprovalSnapshot.annexureId == annexure_id,
            QuotAnnexureApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .order_by(QuotAnnexureApprovalSnapshot.snapshotId.desc())
        .first()
    )
    if snap is None:
        raise HTTPException(404, "No approval snapshot for this annexure yet.")
    return AnnexureApprovalSnapshotDetail(
        snapshotId=snap.snapshotId,
        annexureId=snap.annexureId,
        quotId=snap.quotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        snapshot=json.loads(snap.snapshotData),
    )


@router.get(
    "/annexure/{annexure_id}/approval-snapshots/{snapshot_id}",
    response_model=AnnexureApprovalSnapshotDetail,
)
def get_annexure_snapshot_by_id(
    annexure_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Fetch a specific historical annexure snapshot."""
    import json
    require_permission(MENU, "CanRead", ctx)
    _get_annexure_or_403(db, annexure_id, ctx)
    snap = (
        db.query(QuotAnnexureApprovalSnapshot)
        .filter(
            QuotAnnexureApprovalSnapshot.snapshotId == snapshot_id,
            QuotAnnexureApprovalSnapshot.annexureId == annexure_id,
            QuotAnnexureApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .first()
    )
    if snap is None:
        raise HTTPException(404, "Snapshot not found for this annexure.")
    return AnnexureApprovalSnapshotDetail(
        snapshotId=snap.snapshotId,
        annexureId=snap.annexureId,
        quotId=snap.quotId,
        versionNo=snap.versionNo,
        approvedByUserId=snap.approvedByUserId,
        approvedByName=snap.approvedByName,
        approvedAt=snap.approvedAt,
        snapshot=json.loads(snap.snapshotData),
    )


# ---------------------------------------------------------------------------
# Soft-flow version-switch (load a snapshot into the live editor)
# ---------------------------------------------------------------------------
# Annexure has no child table (diawiseBreakup is in-row JSON), so this
# is a single-row overwrite. Pattern mirrors the FWS + viability load
# endpoints: ``CanEdit`` permission, audit log records the source
# version, caller commits.

@router.post(
    "/annexure/{annexure_id}/approval-snapshots/{snapshot_id}/load",
)
def load_annexure_snapshot(
    annexure_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Restore an annexure snapshot — its frozen content replaces the
    head row's editable fields. User edits forward; next Approve
    creates a forked version (or D3 short-circuits if unchanged)."""
    from app.services.approval_snapshot_service import (
        restore_annexure_from_snapshot,
    )
    try:
        require_permission(MENU, "CanEdit", ctx)
        annexure = _get_annexure_or_403(db, annexure_id, ctx, for_update=True)
        snap = (
            db.query(QuotAnnexureApprovalSnapshot)
            .filter(
                QuotAnnexureApprovalSnapshot.snapshotId == snapshot_id,
                QuotAnnexureApprovalSnapshot.annexureId == annexure_id,
                QuotAnnexureApprovalSnapshot.isActive == True,  # noqa: E712
            )
            .first()
        )
        if snap is None:
            raise HTTPException(404, "Snapshot not found for this annexure.")
        try:
            restore_annexure_from_snapshot(
                db, annexure, snap, user_id=ctx.user_id,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        label = f"V{snap.versionNo}"
        log_action(
            db, quot_id=annexure.quotId, company_id=annexure.companyId,
            action="Annexure Restored from snapshot",
            status=annexure.status, ctx=ctx,
            details=f"annexure #{annexure.annexureId} · restored {label}",
        )
        db.commit()
        return {
            "restoredFromSnapshotId": snap.snapshotId,
            "restoredFromLabel": label,
        }
    except Exception as e:
        log_failure(
            db, quot_id=0, company_id=ctx.company_id,
            action="Annexure Restore", ctx=ctx, exc=e,
        )
        raise
