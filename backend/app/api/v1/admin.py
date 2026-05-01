"""SuperAdmin-only destructive / maintenance endpoints.

Everything here is guarded by `require_super_admin` — a CompanyAdmin cannot
reach these routes.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser, get_db, require_super_admin
from app.models.company import Company
from app.services.data_purge_service import purge_data

router = APIRouter()

# The exact string the user must type in the confirmation field. Must match
# in the frontend too (see DataPurgeComponent).
PURGE_CONFIRMATION = "DELETE ALL ENQUIRIES AND QUOTATIONS"


class DataPurgeRequest(BaseModel):
    companyId: int
    modules: List[str] = Field(
        default_factory=list,
        description="Subset of ['enquiries', 'quotations'] — at least one required.",
    )
    mode: str = Field(
        default="soft",
        description="'soft' (isActive=0) or 'hard' (DELETE rows + storage files).",
    )
    confirmation: str = Field(
        ...,
        description=f"Must equal '{PURGE_CONFIRMATION}' exactly.",
    )
    acknowledgeHardDelete: Optional[bool] = Field(
        default=False,
        description="Required to be true when mode='hard'.",
    )


class DataPurgeResponse(BaseModel):
    ok: bool
    companyId: int
    mode: str
    modules: List[str]
    counts: dict
    filesDeleted: int
    filesFailed: int


@router.post("/data-purge", response_model=DataPurgeResponse)
def data_purge(
    body: DataPurgeRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_super_admin),
):
    """Wipe enquiries / quotations (and cascading children + asset files) for
    one company. SuperAdmin only. Soft by default; hard mode requires explicit
    acknowledgement."""
    # Confirmation string gate — defence-in-depth against accidental API hits.
    if body.confirmation != PURGE_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation string must be '{PURGE_CONFIRMATION}' exactly.",
        )
    if body.mode == "hard" and not body.acknowledgeHardDelete:
        raise HTTPException(
            status_code=400,
            detail="Hard delete requires acknowledgeHardDelete=true.",
        )

    # Validate the target company exists (avoids nuking nothing silently).
    company = db.query(Company).filter(
        Company.companyId == body.companyId,
        Company.isActive == True,
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    try:
        result = purge_data(
            db,
            company_id=body.companyId,
            modules=body.modules,
            mode=body.mode,
            user_id=current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Single transaction: either everything above committed or nothing did.
    db.commit()

    return DataPurgeResponse(
        ok=True,
        companyId=result.companyId,
        mode=result.mode,
        modules=result.modules,
        counts=result.counts,
        filesDeleted=result.filesDeleted,
        filesFailed=result.filesFailed,
    )
