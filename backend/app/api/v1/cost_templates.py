from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.models.cost_template import CostTemplate

router = APIRouter()

COST_FIELDS = [
    "Marketing", "FreightTrailer", "FreightTruck", "Unloading", "OHD", "IFC",
    "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge", "ShortLnthCharge",
    "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation", "Commission", "Misc",
    "Testing", "MOUTOD", "SplDisc", "JC",
]


class CostTemplateCreate(BaseModel):
    templateName: str
    Marketing: Optional[float] = None
    FreightTrailer: Optional[float] = None
    FreightTruck: Optional[float] = None
    Unloading: Optional[float] = None
    OHD: Optional[float] = None
    IFC: Optional[float] = None
    WeighmentDiff: Optional[float] = None
    CD: Optional[float] = None
    SWECharge: Optional[float] = None
    CRS: Optional[float] = None
    IncCharge: Optional[float] = None
    ShortLnthCharge: Optional[float] = None
    SpeciFicLnthCharge: Optional[float] = None
    ExtraCharge: Optional[float] = None
    Fluctuation: Optional[float] = None
    Commission: Optional[float] = None
    Misc: Optional[float] = None
    Testing: Optional[float] = None
    MOUTOD: Optional[float] = None
    SplDisc: Optional[float] = None
    JC: Optional[float] = None


class CostTemplateResponse(CostTemplateCreate):
    templateId: int
    companyId: int
    isActive: bool
    class Config:
        from_attributes = True


@router.get("", response_model=List[CostTemplateResponse])
def list_templates(
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    q = db.query(CostTemplate).filter(
        CostTemplate.companyId == current_user.company_id,
        CostTemplate.isActive == True,
    )
    if search:
        q = q.filter(CostTemplate.templateName.ilike(f"%{search}%"))
    return q.order_by(CostTemplate.templateName).all()


@router.get("/{template_id}", response_model=CostTemplateResponse)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    t = db.query(CostTemplate).filter(
        CostTemplate.templateId == template_id,
        CostTemplate.companyId == current_user.company_id,
        CostTemplate.isActive == True,
    ).first()
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@router.post("", response_model=CostTemplateResponse, status_code=201)
def create_template(
    data: CostTemplateCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    t = CostTemplate(
        **data.model_dump(),
        companyId=current_user.company_id,
        createdby=current_user.user_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    t = db.query(CostTemplate).filter(
        CostTemplate.templateId == template_id,
        CostTemplate.companyId == current_user.company_id,
        CostTemplate.isActive == True,
    ).first()
    if not t:
        raise HTTPException(404, "Template not found")
    t.isActive = False
    t.lastupdateby = current_user.user_id
    db.commit()
