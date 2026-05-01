from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.pagination import PaginationParams, paginate
from app.models.quotation_format import QuotationFormat
from app.schemas.quotation_format import (
    QuotationFormatCreate,
    QuotationFormatUpdate,
    QuotationFormatResponse,
    QuotationFormatListItem,
)

router = APIRouter()


# ===== List (lightweight, no HTML blobs) =====

@router.get("")
def list_formats(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    q = db.query(QuotationFormat).filter(
        QuotationFormat.companyId == current_user.company_id,
        QuotationFormat.isActive == True,
    ).order_by(QuotationFormat.qfId.desc())
    result = paginate(q, pagination)
    result["items"] = [
        QuotationFormatListItem.model_validate(row).model_dump()
        for row in result["items"]
    ]
    return result


# ===== Get current format (for print component) =====

@router.get("/current", response_model=QuotationFormatResponse)
def get_current_format(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fmt = db.query(QuotationFormat).filter(
        QuotationFormat.companyId == current_user.company_id,
        QuotationFormat.isActive == True,
        QuotationFormat.isCurrent == True,
    ).first()
    if not fmt:
        raise HTTPException(status_code=404, detail="No current format set")
    return fmt


# ===== Get single format (full detail with HTML) =====

@router.get("/{qf_id}", response_model=QuotationFormatResponse)
def get_format(
    qf_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fmt = db.query(QuotationFormat).filter(
        QuotationFormat.qfId == qf_id,
        QuotationFormat.companyId == current_user.company_id,
        QuotationFormat.isActive == True,
    ).first()
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    return fmt


# ===== Create =====

@router.post("", response_model=QuotationFormatResponse)
def create_format(
    data: QuotationFormatCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fmt = QuotationFormat(
        companyId=current_user.company_id,
        formatName=data.formatName,
        qHeader=data.qHeader,
        qContent=data.qContent,
        qFooter=data.qFooter,
        isCurrent=data.isCurrent,
        createdby=current_user.user_id,
    )
    if data.isCurrent:
        _unset_current(db, current_user.company_id)
    db.add(fmt)
    db.commit()
    db.refresh(fmt)
    return fmt


# ===== Update =====

@router.put("/{qf_id}", response_model=QuotationFormatResponse)
def update_format(
    qf_id: int,
    data: QuotationFormatUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fmt = db.query(QuotationFormat).filter(
        QuotationFormat.qfId == qf_id,
        QuotationFormat.companyId == current_user.company_id,
        QuotationFormat.isActive == True,
    ).first()
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("isCurrent"):
        _unset_current(db, current_user.company_id, exclude_id=qf_id)
    for key, value in update_data.items():
        setattr(fmt, key, value)
    fmt.lastupdateby = current_user.user_id
    db.commit()
    db.refresh(fmt)
    return fmt


# ===== Set as current =====

@router.patch("/{qf_id}/set-current", response_model=QuotationFormatResponse)
def set_current(
    qf_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fmt = db.query(QuotationFormat).filter(
        QuotationFormat.qfId == qf_id,
        QuotationFormat.companyId == current_user.company_id,
        QuotationFormat.isActive == True,
    ).first()
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    _unset_current(db, current_user.company_id, exclude_id=qf_id)
    fmt.isCurrent = True
    fmt.lastupdateby = current_user.user_id
    db.commit()
    db.refresh(fmt)
    return fmt


# ===== Soft delete =====

@router.delete("/{qf_id}")
def delete_format(
    qf_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    fmt = db.query(QuotationFormat).filter(
        QuotationFormat.qfId == qf_id,
        QuotationFormat.companyId == current_user.company_id,
        QuotationFormat.isActive == True,
    ).first()
    if not fmt:
        raise HTTPException(status_code=404, detail="Format not found")
    fmt.isActive = False
    fmt.lastupdateby = current_user.user_id
    db.commit()
    return {"detail": "Deleted"}


# ===== Helper =====

def _unset_current(db: Session, company_id: int, exclude_id: int = None):
    q = db.query(QuotationFormat).filter(
        QuotationFormat.companyId == company_id,
        QuotationFormat.isActive == True,
        QuotationFormat.isCurrent == True,
    )
    if exclude_id:
        q = q.filter(QuotationFormat.qfId != exclude_id)
    q.update({"isCurrent": False}, synchronize_session="fetch")
