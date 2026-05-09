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
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.timezone import now_ist
from app.models.quot_annexure import QuotAnnexure
from app.models.quotation import QuotSummary
from app.models.user import User
from app.schemas.quot_annexure import AnnexureResponse, AnnexureUpdate, DiaBreakupEntry
from app.services.access_service import AccessContext, get_access_context, require_permission
from app.services.annexure_service import deserialize_breakup, generate_annexure
from app.services.activity_log_service import log_action, log_failure

MENU = "Quotations"

router = APIRouter()


def _get_quotation_or_403(db: Session, quot_id: int, ctx: AccessContext) -> QuotSummary:
    from app.api.v1.quotations import _get_quot_or_403  # noqa: WPS433
    return _get_quot_or_403(db, quot_id, ctx)


def _get_annexure_or_403(db: Session, annexure_id: int, ctx: AccessContext) -> QuotAnnexure:
    ann = (
        db.query(QuotAnnexure)
        .filter(
            QuotAnnexure.annexureId == annexure_id,
            QuotAnnexure.isActive == True,
        )
        .first()
    )
    if not ann:
        raise HTTPException(404, "Annexure not found")
    _get_quotation_or_403(db, ann.quotId, ctx)
    return ann


def _to_response(ann: QuotAnnexure) -> dict:
    """Convert ORM → response dict (deserializes the stored JSON breakup)."""
    data = {c.key: getattr(ann, c.key) for c in QuotAnnexure.__table__.columns}
    data["diawiseBreakup"] = deserialize_breakup(ann.diawiseBreakup)
    return data


@router.post("/quotations/{quot_id}/annexure", response_model=AnnexureResponse)
def create_annexure(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Generate annexure from quotation + viability. Idempotent."""
    try:
        require_permission(MENU, "CanEdit", ctx)
        quotation = _get_quotation_or_403(db, quot_id, ctx)
        try:
            annexure = generate_annexure(db, quotation=quotation, user_id=ctx.user_id)
        except ValueError as e:
            raise HTTPException(400, str(e))

        # Phase 1: per-stage statuses are the source of truth. The
        # annexure has its own ``status``='Draft' on creation; the
        # parent quotation stays at 'Converted'.
        log_action(db, quot_id=quotation.quotId, company_id=quotation.companyId,
                   action="Annexure Generated", status=quotation.status, user_id=ctx.user_id)

        db.commit()
        db.refresh(annexure)
        return _to_response(annexure)
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Generate Annexure", user_id=ctx.user_id, exc=e)
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
    ann = _get_annexure_or_403(db, annexure_id, ctx)
    # Locked once approved — except for users with the
    # ``CanApproveAnnexure`` flag (the Commercial HOD role), who keep
    # editing rights post-approval so corrections can be applied to a
    # signed-off annexure without a full revision cycle.
    if ann.status == "Approved" and not ctx.has_permission(MENU, "CanApproveAnnexure"):
        raise HTTPException(400, "Annexure is Approved and locked for edits.")

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
                   user_id=ctx.user_id,
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
        ann = _get_annexure_or_403(db, annexure_id, ctx)
        if ann.status == "Approved":
            return _to_response(ann)

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

        # Phase 1: per-stage statuses are the source of truth. The
        # annexure's ``status`` flips to 'Approved'; the parent
        # quotation stays at 'Converted'.
        quotation = db.query(QuotSummary).filter(QuotSummary.quotId == ann.quotId).first()
        log_action(db, quot_id=ann.quotId, company_id=ann.companyId,
                   action="Annexure Approved",
                   status=quotation.status if quotation else None,
                   user_id=ctx.user_id)

        db.commit()
        db.refresh(ann)
        return _to_response(ann)
    except Exception as e:
        if quot_id_for_log:
            log_failure(db, quot_id=quot_id_for_log, company_id=ctx.company_id,
                        action="Approve Annexure", user_id=ctx.user_id, exc=e)
        raise
