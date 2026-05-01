from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.timezone import now_ist
from app.models.ownership_transfer import OwnershipTransfer
from app.models.enquiry import CustomerEnquiry
from app.models.quotation import QuotSummary
from app.models.user import User
from app.models.role import Role
from app.schemas.ownership_transfer import TransferRequest, TransferAction, TransferResponse

router = APIRouter()


def _build_response(t: OwnershipTransfer, db: Session) -> dict:
    """Build transfer response with user names."""
    def _name(uid):
        if not uid:
            return None
        u = db.query(User.userName).filter(User.userId == uid).first()
        return u.userName if u else None

    return {
        "transferId": t.transferId,
        "companyId": t.companyId,
        "entityType": t.entityType,
        "entityId": t.entityId,
        "fromUserId": t.fromUserId,
        "fromUserName": _name(t.fromUserId),
        "toUserId": t.toUserId,
        "toUserName": _name(t.toUserId),
        "requestedBy": t.requestedBy,
        "requestedByName": _name(t.requestedBy),
        "requestedOn": t.requestedOn,
        "status": t.status,
        "approvedBy": t.approvedBy,
        "approvedByName": _name(t.approvedBy),
        "approvedOn": t.approvedOn,
        "remarks": t.remarks,
    }


@router.post("", status_code=201)
def request_transfer(
    data: TransferRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Request ownership transfer for an enquiry or quotation."""
    if data.entityType not in ("enquiry", "quotation"):
        raise HTTPException(400, "entityType must be 'enquiry' or 'quotation'")

    # Get current owner
    if data.entityType == "enquiry":
        record = db.query(CustomerEnquiry).filter(
            CustomerEnquiry.enqid == data.entityId,
            CustomerEnquiry.companyId == current_user.company_id,
            CustomerEnquiry.isActive == True,
        ).first()
        from_user_id = record.ownerUserId if record else None
    else:
        record = db.query(QuotSummary).filter(
            QuotSummary.quotId == data.entityId,
            QuotSummary.companyId == current_user.company_id,
            QuotSummary.isActive == True,
        ).first()
        from_user_id = record.ownerUserId if record else None

    if not record:
        raise HTTPException(404, "Record not found")
    if not from_user_id:
        from_user_id = record.createdby

    # Check no pending transfer exists
    existing = db.query(OwnershipTransfer).filter(
        OwnershipTransfer.entityType == data.entityType,
        OwnershipTransfer.entityId == data.entityId,
        OwnershipTransfer.status == "pending",
        OwnershipTransfer.isActive == True,
    ).first()
    if existing:
        raise HTTPException(400, "A pending transfer already exists for this record")

    transfer = OwnershipTransfer(
        companyId=current_user.company_id,
        entityType=data.entityType,
        entityId=data.entityId,
        fromUserId=from_user_id,
        toUserId=data.toUserId,
        requestedBy=current_user.user_id,
        requestedOn=now_ist(),
        status="pending",
        remarks=data.remarks,
        createdby=current_user.user_id,
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return _build_response(transfer, db)


@router.get("/pending", response_model=List[TransferResponse])
def get_pending_transfers(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get pending transfers. Only users with canApproveTransfers or SuperAdmin can see all."""
    role = db.query(Role).filter(Role.roleId == current_user.role_id).first()
    can_approve = current_user.is_super_admin or (role and role.canApproveTransfers)

    q = db.query(OwnershipTransfer).filter(
        OwnershipTransfer.companyId == current_user.company_id,
        OwnershipTransfer.status == "pending",
        OwnershipTransfer.isActive == True,
    )
    if not can_approve:
        # Non-approvers only see their own requests
        q = q.filter(OwnershipTransfer.requestedBy == current_user.user_id)

    transfers = q.order_by(OwnershipTransfer.requestedOn.desc()).all()
    return [_build_response(t, db) for t in transfers]


@router.get("/history", response_model=List[TransferResponse])
def get_transfer_history(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all transfers (approved/rejected) for the company."""
    transfers = db.query(OwnershipTransfer).filter(
        OwnershipTransfer.companyId == current_user.company_id,
        OwnershipTransfer.status != "pending",
        OwnershipTransfer.isActive == True,
    ).order_by(OwnershipTransfer.approvedOn.desc()).limit(100).all()
    return [_build_response(t, db) for t in transfers]


@router.post("/{transfer_id}/approve")
def approve_transfer(
    transfer_id: int,
    data: TransferAction,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Approve a pending transfer. Requires canApproveTransfers or SuperAdmin."""
    role = db.query(Role).filter(Role.roleId == current_user.role_id).first()
    if not (current_user.is_super_admin or (role and role.canApproveTransfers)):
        raise HTTPException(403, "You do not have permission to approve transfers")

    transfer = db.query(OwnershipTransfer).filter(
        OwnershipTransfer.transferId == transfer_id,
        OwnershipTransfer.companyId == current_user.company_id,
        OwnershipTransfer.status == "pending",
        OwnershipTransfer.isActive == True,
    ).first()
    if not transfer:
        raise HTTPException(404, "Transfer not found or already processed")

    # Update the record's owner
    if transfer.entityType == "enquiry":
        record = db.query(CustomerEnquiry).filter(
            CustomerEnquiry.enqid == transfer.entityId,
        ).first()
        if record:
            record.ownerUserId = transfer.toUserId
            # Update ownerRoleId from the new owner's role mapping
            from app.models.user import UserRoleMap
            mapping = db.query(UserRoleMap).filter(
                UserRoleMap.userId == transfer.toUserId,
                UserRoleMap.companyId == current_user.company_id,
                UserRoleMap.isActive == True,
            ).first()
            if mapping:
                record.ownerRoleId = mapping.roleId
    else:
        record = db.query(QuotSummary).filter(
            QuotSummary.quotId == transfer.entityId,
        ).first()
        if record:
            record.ownerUserId = transfer.toUserId
            from app.models.user import UserRoleMap
            mapping = db.query(UserRoleMap).filter(
                UserRoleMap.userId == transfer.toUserId,
                UserRoleMap.companyId == current_user.company_id,
                UserRoleMap.isActive == True,
            ).first()
            if mapping:
                record.ownerRoleId = mapping.roleId

    transfer.status = "approved"
    transfer.approvedBy = current_user.user_id
    transfer.approvedOn = now_ist()
    if data.remarks:
        transfer.remarks = (transfer.remarks or "") + f" | Approved: {data.remarks}"
    transfer.lastupdateby = current_user.user_id

    db.commit()
    return {"message": "Transfer approved", "transferId": transfer_id}


@router.post("/{transfer_id}/reject")
def reject_transfer(
    transfer_id: int,
    data: TransferAction,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reject a pending transfer."""
    role = db.query(Role).filter(Role.roleId == current_user.role_id).first()
    if not (current_user.is_super_admin or (role and role.canApproveTransfers)):
        raise HTTPException(403, "You do not have permission to reject transfers")

    transfer = db.query(OwnershipTransfer).filter(
        OwnershipTransfer.transferId == transfer_id,
        OwnershipTransfer.companyId == current_user.company_id,
        OwnershipTransfer.status == "pending",
        OwnershipTransfer.isActive == True,
    ).first()
    if not transfer:
        raise HTTPException(404, "Transfer not found or already processed")

    transfer.status = "rejected"
    transfer.approvedBy = current_user.user_id
    transfer.approvedOn = now_ist()
    if data.remarks:
        transfer.remarks = (transfer.remarks or "") + f" | Rejected: {data.remarks}"
    transfer.lastupdateby = current_user.user_id

    db.commit()
    return {"message": "Transfer rejected", "transferId": transfer_id}
