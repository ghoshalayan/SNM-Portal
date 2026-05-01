from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db, require_super_admin, CurrentUser
from app.models.company import Company
from app.schemas.company import CompanyCreate, CompanyUpdate, CompanyResponse
from app.services.company_setup_service import seed_company_defaults, seed_superadmin_for_all_companies

router = APIRouter()


@router.get("", response_model=List[CompanyResponse])
def get_companies(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    return db.query(Company).filter(Company.isActive == True).all()


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    company = db.query(Company).filter(
        Company.companyId == company_id,
        Company.isActive == True,
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    company = Company(**data.model_dump(), createdby=current_user.user_id)
    db.add(company)
    db.flush()  # get companyId before seeding defaults
    seed_company_defaults(db, company.companyId, current_user.user_id)
    db.commit()
    db.refresh(company)
    return company


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    company = db.query(Company).filter(
        Company.companyId == company_id,
        Company.isActive == True,
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)
    company.lastupdateby = current_user.user_id
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    company = db.query(Company).filter(
        Company.companyId == company_id,
        Company.isActive == True,
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    company.isActive = False
    company.lastupdateby = current_user.user_id
    db.commit()


@router.post("/seed-superadmin", status_code=status.HTTP_200_OK)
def backfill_superadmin(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    """Backfill: ensure every company has a SuperAdmin role and all SA users are mapped.
    Safe to call multiple times — idempotent."""
    result = seed_superadmin_for_all_companies(db, current_user.user_id)
    db.commit()
    return result
