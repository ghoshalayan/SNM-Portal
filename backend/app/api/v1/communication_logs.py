from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.core.dependencies import get_db
from app.core.pagination import PaginationParams, paginate
from app.models.communication import CommunicationLog
from app.services.access_service import (
    AccessContext, get_access_context,
    apply_company_filter, apply_hierarchy_filter,
    require_permission,
)

router = APIRouter()

MENU = "Communication Logs"


# ========== Schemas ==========

class CommunicationLogCreate(BaseModel):
    commmode: Optional[str] = None
    contactto: Optional[str] = None
    contactinfo: Optional[str] = None
    enqid: Optional[int] = None
    quoteid: Optional[int] = None
    commsubject: Optional[str] = None
    commdescription: Optional[str] = None


class CommunicationLogResponse(BaseModel):
    commlogID: int
    companyId: int
    commmode: Optional[str] = None
    contactto: Optional[str] = None
    contactinfo: Optional[str] = None
    enqid: Optional[int] = None
    quoteid: Optional[int] = None
    commsubject: Optional[str] = None
    commdescription: Optional[str] = None
    ownerUserId: Optional[int] = None
    createdon: Optional[datetime] = None
    createdby: Optional[int] = None
    isActive: bool

    class Config:
        from_attributes = True


# ========== Endpoints ==========

@router.get("")
def list_communication_logs(
    enqid: Optional[int] = Query(None),
    quoteid: Optional[int] = Query(None),
    commmode: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    q = db.query(CommunicationLog).filter(CommunicationLog.isActive == True)
    q = apply_company_filter(q, CommunicationLog.companyId, ctx)
    q = apply_hierarchy_filter(q, CommunicationLog.ownerUserId, ctx)

    if enqid:
        q = q.filter(CommunicationLog.enqid == enqid)
    if quoteid:
        q = q.filter(CommunicationLog.quoteid == quoteid)
    if commmode:
        q = q.filter(CommunicationLog.commmode == commmode)
    if pagination.search:
        q = q.filter(
            CommunicationLog.commsubject.ilike(f"%{pagination.search}%")
            | CommunicationLog.contactto.ilike(f"%{pagination.search}%")
        )
    q = q.order_by(CommunicationLog.commlogID.desc())
    return paginate(q, pagination)


def _get_log_or_403(db: Session, log_id: int, ctx: AccessContext) -> CommunicationLog:
    log = db.query(CommunicationLog).filter(
        CommunicationLog.commlogID == log_id,
        CommunicationLog.isActive == True,
    )
    log = apply_company_filter(log, CommunicationLog.companyId, ctx)
    log = apply_hierarchy_filter(log, CommunicationLog.ownerUserId, ctx)
    result = log.first()
    if not result:
        raise HTTPException(status_code=404, detail="Communication log not found")
    return result


@router.get("/{log_id}", response_model=CommunicationLogResponse)
def get_communication_log(
    log_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    return _get_log_or_403(db, log_id, ctx)


@router.post("", response_model=CommunicationLogResponse, status_code=201)
def create_communication_log(
    data: CommunicationLogCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanAdd", ctx)
    log = CommunicationLog(
        **data.model_dump(),
        companyId=ctx.company_id,
        ownerUserId=ctx.user_id,
        ownerRoleId=ctx.role_id,
        createdby=ctx.user_id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.put("/{log_id}", response_model=CommunicationLogResponse)
def update_communication_log(
    log_id: int,
    data: CommunicationLogCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    log = _get_log_or_403(db, log_id, ctx)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(log, k, v)
    log.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(log)
    return log


@router.delete("/{log_id}", status_code=204)
def delete_communication_log(
    log_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanDelete", ctx)
    log = _get_log_or_403(db, log_id, ctx)
    log.isActive = False
    log.lastupdateby = ctx.user_id
    db.commit()
