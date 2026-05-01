from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date
from app.core.timezone import now_ist
from pydantic import BaseModel

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.pagination import PaginationParams, paginate
from app.core.cursor_pagination import CursorParams, cursor_paginate
from app.models.enquiry import CustomerEnquiry, CustomerEnquiryDetails, CustomerEnquiryCosting, CustomerEnqFollowUp
from app.models.customer import CustomerMaster, CustomerSite
from app.models.financial_year import FinancialYear
from app.models.user import User  # used in followup/costing endpoints
from app.schemas.enquiry import (
    EnquiryCreate, EnquiryUpdate, EnquiryResponse,
    EnquiryDetailCreate, EnquiryDetailResponse,
    EnquiryCostingCreate, EnquiryCostingResponse,
    FollowUpCreate, FollowUpResponse,
)
from app.services.costing_service import get_tp_cost_for_dia, create_new_costing_version
from app.services.access_service import (
    AccessContext, get_access_context,
    apply_company_filter, apply_hierarchy_filter, apply_location_filter,
    require_permission, require_owner_visible, require_location_access,
    require_parent_visible,
)

router = APIRouter()

MENU = "Enquiries"


# ===== Search (cursor-based, for dropdown lookups) =====

@router.get("/search")
def search_enquiries(
    params: CursorParams = Depends(),
    excludeStatuses: Optional[str] = Query(
        None,
        description="Comma-separated list of status values to exclude (e.g. 'Quotation Prepared,Reject').",
    ),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Cursor-paginated enquiry search for dropdowns (e.g. Quotation form's
    Source Enquiry picker). Scales to 50k+ rows.

    - Prefix-matches enqNo
    - Applies F2/F5 visibility (company + hierarchy owner filter)
    - Optionally excludes enquiries whose status is in excludeStatuses
      (used by the quotation form to hide already-quoted and rejected enquiries)
    - Returns latest first (descending enqid)
    """
    require_permission(MENU, "CanRead", ctx)

    q = db.query(
        CustomerEnquiry.enqid,
        CustomerEnquiry.enqNo,
        CustomerEnquiry.customerId,
        CustomerEnquiry.enqDate,
        CustomerMaster.customerName,
    ).join(
        CustomerMaster, CustomerEnquiry.customerId == CustomerMaster.customerId,
    ).filter(CustomerEnquiry.isActive == True)
    q = apply_company_filter(q, CustomerEnquiry.companyId, ctx)
    q = apply_hierarchy_filter(q, CustomerEnquiry.ownerUserId, ctx)

    # id-lookup mode — runs before excludeStatuses so an already-linked enquiry
    # can still resolve its label even if its status has since moved into
    # the excluded list (e.g. viewing an old quotation whose source enquiry
    # is now 'Quotation Prepared')
    if params.ids:
        rows = q.filter(CustomerEnquiry.enqid.in_(params.ids)).all()
        return {
            "items": [
                {
                    "id": r.enqid, "label": r.enqNo, "sub": r.customerName,
                    "enqDate": r.enqDate, "customerId": r.customerId,
                }
                for r in rows
            ],
            "nextCursor": None, "hasMore": False,
        }

    if excludeStatuses:
        blocked = [s.strip() for s in excludeStatuses.split(",") if s.strip()]
        if blocked:
            q = q.filter(~CustomerEnquiry.status.in_(blocked))

    if params.q:
        term = f"%{params.q}%"  # substring on enqNo (short field, ok without prefix)
        q = q.filter(CustomerEnquiry.enqNo.ilike(term))

    rows, next_cursor, has_more = cursor_paginate(
        q, CustomerEnquiry.enqid, params, descending=True,
    )
    return {
        "items": [
            {
                "id": r.enqid,
                "label": r.enqNo,
                "sub": r.customerName,
                "enqDate": r.enqDate,
                "customerId": r.customerId,
            }
            for r in rows
        ],
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


# ===== Enquiry Header =====

@router.get("")
def get_enquiries(
    customerId: Optional[int] = Query(None),
    dateFrom: Optional[date] = Query(None),
    dateTo: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)

    q = db.query(
        CustomerEnquiry.enqid,
        CustomerEnquiry.companyId,
        CustomerEnquiry.customerId,
        CustomerMaster.customerName,
        CustomerEnquiry.customerContactId,
        CustomerEnquiry.siteId,
        CustomerEnquiry.enqNo,
        CustomerEnquiry.enqDate,
        CustomerEnquiry.enqMode,
        CustomerEnquiry.description,
        CustomerEnquiry.validityDays,
        CustomerEnquiry.status,
        CustomerEnquiry.isActive,
        CustomerEnquiry.createdon,
    ).join(
        CustomerMaster, CustomerEnquiry.customerId == CustomerMaster.customerId,
    ).outerjoin(
        CustomerSite, CustomerEnquiry.siteId == CustomerSite.siteId,
    ).filter(CustomerEnquiry.isActive == True)

    # F2 + F5 + F6
    q = apply_company_filter(q, CustomerEnquiry.companyId, ctx)
    q = apply_hierarchy_filter(q, CustomerEnquiry.ownerUserId, ctx)
    q = apply_location_filter(q, CustomerSite.state, CustomerSite.dist, ctx,
                              nullable_fk=CustomerEnquiry.siteId)

    if customerId:
        q = q.filter(CustomerEnquiry.customerId == customerId)
    if dateFrom:
        q = q.filter(CustomerEnquiry.enqDate >= dateFrom)
    if dateTo:
        q = q.filter(CustomerEnquiry.enqDate <= dateTo)
    if status:
        q = q.filter(CustomerEnquiry.status == status)
    if pagination.search:
        q = q.filter(CustomerEnquiry.enqNo.ilike(f"%{pagination.search}%"))

    from app.core.pagination import resolve_sort_column
    _ALLOWED_ENQ_SORT = {
        "enqid",            # default list sort (desc)
        "enqNo", "enqDate", "enqMode", "status", "validityDays",
        "createdon", "lastupdateon",
    }
    sort_col = resolve_sort_column(
        CustomerEnquiry, pagination.sort_by, allowed=_ALLOWED_ENQ_SORT,
    )
    if sort_col is not None:
        q = q.order_by(sort_col.desc() if pagination.sort_dir == "desc" else sort_col.asc())
    else:
        q = q.order_by(CustomerEnquiry.enqid.desc())

    result = paginate(q, pagination)
    result["items"] = [
        {
            "enqid": row.enqid,
            "companyId": row.companyId,
            "customerId": row.customerId,
            "customerName": row.customerName,
            "customerContactId": row.customerContactId,
            "siteId": row.siteId,
            "enqNo": row.enqNo,
            "enqDate": row.enqDate,
            "enqMode": row.enqMode,
            "description": row.description,
            "validityDays": row.validityDays,
            "status": row.status,
            "isActive": row.isActive,
            "createdon": row.createdon,
        }
        for row in result["items"]
    ]
    return result


def _get_enquiry_or_403(db: Session, enq_id: int, ctx: AccessContext) -> CustomerEnquiry:
    """Fetch enquiry with F2/F5/F6 checks. Raises 404/403 on failure."""
    q = db.query(CustomerEnquiry).outerjoin(
        CustomerSite, CustomerEnquiry.siteId == CustomerSite.siteId,
    ).filter(
        CustomerEnquiry.enqid == enq_id,
        CustomerEnquiry.isActive == True,
    )
    q = apply_company_filter(q, CustomerEnquiry.companyId, ctx)
    q = apply_hierarchy_filter(q, CustomerEnquiry.ownerUserId, ctx)
    q = apply_location_filter(q, CustomerSite.state, CustomerSite.dist, ctx,
                              nullable_fk=CustomerEnquiry.siteId)
    enq = q.first()
    if not enq:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    return enq


@router.get("/{enq_id}", response_model=EnquiryResponse)
def get_enquiry(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    return _get_enquiry_or_403(db, enq_id, ctx)


@router.post("", response_model=EnquiryResponse, status_code=201)
def create_enquiry(
    data: EnquiryCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
    current_user: CurrentUser = Depends(get_current_user),
):
    require_permission(MENU, "CanAdd", ctx)
    from app.services.owner_resolver import resolve_owner

    # F6: Site location access — scope fetch to this tenant so a site ID
    # from another company can never be attached to an enquiry here.
    if data.siteId:
        site = db.query(CustomerSite).filter(
            CustomerSite.siteId == data.siteId,
            CustomerSite.companyId == ctx.company_id,
            CustomerSite.isActive == True,
        ).first()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        require_location_access(
            site.state, site.dist, ctx,
            detail="You do not have access to this site's location",
        )

    data_dict = data.model_dump()
    code_user_id = data_dict.pop("codeUserId", None)

    # Owner resolution (uses numGenMode + select-code permission)
    if code_user_id and ctx.role and ctx.role.numGenMode == "select_code":
        # Require CanGenerateUnderOthers permission
        if not ctx.has_permission(MENU, "CanGenerateUnderOthers"):
            raise HTTPException(
                403, "You do not have permission to generate numbers under other users",
            )
    owner = resolve_owner(db, current_user, code_user_id)

    # F7: Auto-generate enqNo with retry on filtered-unique collision.
    user_supplied_enq_no = data_dict.get("enqNo")
    fy_code: Optional[str] = None
    if not user_supplied_enq_no:
        fy = db.query(FinancialYear).filter(
            FinancialYear.companyId == ctx.company_id,
            FinancialYear.isCurrent == True,
            FinancialYear.isActive == True,
        ).first()
        if not fy:
            raise HTTPException(400, "No current Financial Year set for this company")
        fy_code = fy.fyCode

    def _next_enq_no() -> str:
        if user_supplied_enq_no:
            return user_supplied_enq_no
        count = db.query(func.count(CustomerEnquiry.enqid)).filter(
            CustomerEnquiry.companyId == ctx.company_id,
            CustomerEnquiry.enqNo.like(f"ENQ-%-{fy_code}-%"),
        ).scalar() or 0
        return f"ENQ-{owner['userCode']}-{fy_code}-{count + 1:04d}"

    def _build_enq(enq_no: str) -> CustomerEnquiry:
        return CustomerEnquiry(
            **{**data_dict, "enqNo": enq_no},
            companyId=ctx.company_id,
            ownerUserId=owner["userId"],
            ownerRoleId=owner["roleId"],
            createdby=ctx.user_id,
        )

    from app.services.number_allocator import allocate_and_flush
    enq = allocate_and_flush(
        db,
        build=_build_enq,
        compute_number=_next_enq_no,
        max_attempts=1 if user_supplied_enq_no else 10,
        conflict_message=(
            "Enquiry number already exists — choose a different one."
            if user_supplied_enq_no
            else "Could not allocate a unique enquiry number after retries."
        ),
    )
    db.commit()
    db.refresh(enq)
    return enq


@router.put("/{enq_id}", response_model=EnquiryResponse)
def update_enquiry(
    enq_id: int,
    data: EnquiryUpdate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    enq = _get_enquiry_or_403(db, enq_id, ctx)
    # Locked if a quotation was drafted from this enquiry
    if enq.status in ("Quotation Prepared",):
        raise HTTPException(400, "This enquiry is locked — a quotation has been prepared from it")
    if enq.status in ("Reject", "Expired"):
        raise HTTPException(400, f"Cannot edit a {enq.status} enquiry")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(enq, k, v)
    enq.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(enq)
    return enq


@router.put("/{enq_id}/reject", response_model=EnquiryResponse)
def reject_enquiry(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Reject an enquiry."""
    require_permission(MENU, "CanEdit", ctx)
    enq = _get_enquiry_or_403(db, enq_id, ctx)
    if enq.status == "Quotation Prepared":
        raise HTTPException(400, "Cannot reject — a quotation has been prepared from this enquiry")
    enq.status = "Reject"
    enq.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(enq)
    return enq


@router.put("/{enq_id}/renew", response_model=EnquiryResponse)
def renew_enquiry(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Renew a Rejected or Expired enquiry back to New for editing.
    Requires CanApprove permission on Enquiries menu.
    """
    # Check CanApprove first; fall back to CanEdit for backward compat
    if not (ctx.has_permission(MENU, "CanApprove") or ctx.has_permission(MENU, "CanEdit")):
        raise HTTPException(403, "Permission denied: renewal requires Approve or Edit permission on Enquiries")
    enq = _get_enquiry_or_403(db, enq_id, ctx)
    if enq.status not in ("Reject", "Expired"):
        raise HTTPException(400, f"Only Rejected or Expired enquiries can be renewed (current: {enq.status})")
    enq.status = "New"
    enq.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(enq)
    return enq


@router.delete("/{enq_id}", status_code=204)
def delete_enquiry(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanDelete", ctx)
    enq = _get_enquiry_or_403(db, enq_id, ctx)
    enq.isActive = False
    enq.lastupdateby = ctx.user_id
    db.commit()


# ===== Ownership Handover =====

class HandoverRequest(BaseModel):
    targetUserId: int
    remarks: Optional[str] = None


@router.post("/{enq_id}/handover")
def handover_enquiry(
    enq_id: int,
    payload: HandoverRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Transfer ownership of an enquiry to another user.
    Requires CanTransferOwnership permission.
    Both source (current owner) and target must be visible to the initiator.
    """
    require_permission(MENU, "CanTransferOwnership", ctx)

    enq = _get_enquiry_or_403(db, enq_id, ctx)

    # Lock guard — once a quotation has been drafted from this enquiry, or
    # it was rejected / expired, ownership is frozen. Mirrors the /update
    # and /reject guards so handover can't sneak around them.
    if enq.status in ("Quotation Prepared", "Reject", "Expired"):
        raise HTTPException(
            400,
            f"Cannot handover — enquiry is {enq.status} and locked.",
        )

    # Source check is implicit — _get_enquiry_or_403 already enforced F5.
    # Validate target is visible to initiator.
    require_owner_visible(payload.targetUserId, ctx)

    # Validate target is active and in same company
    target_user = db.query(User).filter(
        User.userId == payload.targetUserId,
        User.companyId == ctx.company_id,
        User.isActive == True,
    ).first()
    if not target_user:
        raise HTTPException(404, "Target user not found in company")

    # Resolve target's active role in current company
    from app.models.user import UserRoleMap
    urm = db.query(UserRoleMap).filter(
        UserRoleMap.userId == target_user.userId,
        UserRoleMap.companyId == ctx.company_id,
        UserRoleMap.isActive == True,
    ).first()

    enq.ownerUserId = target_user.userId
    enq.ownerRoleId = urm.roleId if urm else None
    enq.lastupdateby = ctx.user_id
    enq.lastupdateon = now_ist()
    db.commit()
    db.refresh(enq)
    return {
        "message": "Enquiry ownership transferred",
        "enqid": enq.enqid,
        "newOwnerUserId": enq.ownerUserId,
    }


# ===== Enquiry Details (Line Items) =====

@router.get("/{enq_id}/details", response_model=List[EnquiryDetailResponse])
def get_enquiry_details(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    return db.query(CustomerEnquiryDetails).filter(
        CustomerEnquiryDetails.enqid == enq_id,
        CustomerEnquiryDetails.companyId == ctx.company_id,
        CustomerEnquiryDetails.isActive == True,
    ).all()


@router.post("/{enq_id}/details", response_model=EnquiryDetailResponse, status_code=201)
def create_enquiry_detail(
    enq_id: int,
    data: EnquiryDetailCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    detail = CustomerEnquiryDetails(
        **data.model_dump(),
        enqid=enq_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(detail)
    db.commit()
    db.refresh(detail)
    return detail


@router.put("/{enq_id}/details/{dtl_id}", response_model=EnquiryDetailResponse)
def update_enquiry_detail(
    enq_id: int,
    dtl_id: int,
    data: EnquiryDetailCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    detail = db.query(CustomerEnquiryDetails).filter(
        CustomerEnquiryDetails.enqdtlid == dtl_id,
        CustomerEnquiryDetails.enqid == enq_id,
        CustomerEnquiryDetails.isActive == True,
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Detail not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(detail, k, v)
    detail.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(detail)
    return detail


@router.delete("/{enq_id}/details/{dtl_id}", status_code=204)
def delete_enquiry_detail(
    enq_id: int,
    dtl_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    detail = db.query(CustomerEnquiryDetails).filter(
        CustomerEnquiryDetails.enqdtlid == dtl_id,
        CustomerEnquiryDetails.enqid == enq_id,
        CustomerEnquiryDetails.isActive == True,
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Detail not found")
    detail.isActive = False
    detail.lastupdateby = ctx.user_id
    db.commit()


# ===== Enquiry Costing (Versioned) =====

@router.get("/{enq_id}/costing", response_model=List[EnquiryCostingResponse])
def get_enquiry_costing(
    enq_id: int,
    version: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    q = db.query(CustomerEnquiryCosting).filter(
        CustomerEnquiryCosting.enqid == enq_id,
        CustomerEnquiryCosting.companyId == ctx.company_id,
        CustomerEnquiryCosting.isActive == True,
    )
    if version:
        q = q.filter(CustomerEnquiryCosting.versionNo == version)
    else:
        max_ver = (
            db.query(func.max(CustomerEnquiryCosting.versionNo))
            .filter(
                CustomerEnquiryCosting.enqid == enq_id,
                CustomerEnquiryCosting.isActive == True,
            )
            .scalar()
        )
        if max_ver:
            q = q.filter(CustomerEnquiryCosting.versionNo == max_ver)
    return q.all()


@router.get("/{enq_id}/costing/versions")
def get_costing_versions(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    versions = (
        db.query(CustomerEnquiryCosting.versionNo)
        .filter(
            CustomerEnquiryCosting.enqid == enq_id,
            CustomerEnquiryCosting.isActive == True,
        )
        .distinct()
        .order_by(CustomerEnquiryCosting.versionNo.desc())
        .all()
    )
    return [v[0] for v in versions]


@router.post("/{enq_id}/costing", response_model=EnquiryCostingResponse, status_code=201)
def save_enquiry_costing(
    enq_id: int,
    data: EnquiryCostingCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)

    max_ver = (
        db.query(func.max(CustomerEnquiryCosting.versionNo))
        .filter(
            CustomerEnquiryCosting.enqid == enq_id,
            CustomerEnquiryCosting.isActive == True,
        )
        .scalar()
    ) or 1

    existing = db.query(CustomerEnquiryCosting).filter(
        CustomerEnquiryCosting.enqid == enq_id,
        CustomerEnquiryCosting.enqdtlid == data.enqdtlid,
        CustomerEnquiryCosting.versionNo == max_ver,
        CustomerEnquiryCosting.isActive == True,
    ).first()

    if existing:
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(existing, k, v)
        existing.lastupdateby = ctx.user_id
        db.commit()
        db.refresh(existing)
        return existing
    else:
        costing = CustomerEnquiryCosting(
            **data.model_dump(),
            enqid=enq_id,
            companyId=ctx.company_id,
            versionNo=max_ver,
            createdby=ctx.user_id,
        )
        db.add(costing)
        db.commit()
        db.refresh(costing)
        return costing


@router.post("/{enq_id}/costing/new-version")
def create_costing_new_version(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    new_costings = create_new_costing_version(
        db, enq_id, ctx.company_id, ctx.user_id,
    )
    return {
        "message": "New version created",
        "versionNo": new_costings[0].versionNo if new_costings else 1,
        "count": len(new_costings),
    }


@router.get("/{enq_id}/costing/auto-fill/{dia}")
def auto_fill_tp_cost(
    enq_id: int,
    dia: str,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    tp_cost = get_tp_cost_for_dia(db, ctx.company_id, dia)
    return {"dia": dia, "tpcost": tp_cost}


# ===== Enquiry Follow-Ups =====

@router.get("/{enq_id}/followups", response_model=List[FollowUpResponse])
def get_followups(
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    return db.query(CustomerEnqFollowUp).filter(
        CustomerEnqFollowUp.enqid == enq_id,
        CustomerEnqFollowUp.companyId == ctx.company_id,
        CustomerEnqFollowUp.isActive == True,
    ).order_by(CustomerEnqFollowUp.followupdate.desc()).all()


@router.post("/{enq_id}/followups", response_model=FollowUpResponse, status_code=201)
def create_followup(
    enq_id: int,
    data: FollowUpCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    followup = CustomerEnqFollowUp(
        **data.model_dump(),
        enqid=enq_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


@router.put("/{enq_id}/followups/{followup_id}", response_model=FollowUpResponse)
def update_followup(
    enq_id: int,
    followup_id: int,
    data: FollowUpCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    followup = db.query(CustomerEnqFollowUp).filter(
        CustomerEnqFollowUp.engfollowupid == followup_id,
        CustomerEnqFollowUp.enqid == enq_id,
        CustomerEnqFollowUp.companyId == ctx.company_id,
        CustomerEnqFollowUp.isActive == True,
    ).first()
    if not followup:
        raise HTTPException(404, "Follow-up not found")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(followup, key, val)
    followup.lastupdateby = ctx.user_id
    followup.lastupdateon = now_ist()
    db.commit()
    db.refresh(followup)
    return followup


@router.delete("/{enq_id}/followups/{followup_id}")
def delete_followup(
    enq_id: int,
    followup_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_enquiry_or_403(db, enq_id, ctx)
    require_parent_visible(parent, ctx)
    followup = db.query(CustomerEnqFollowUp).filter(
        CustomerEnqFollowUp.engfollowupid == followup_id,
        CustomerEnqFollowUp.enqid == enq_id,
        CustomerEnqFollowUp.companyId == ctx.company_id,
        CustomerEnqFollowUp.isActive == True,
    ).first()
    if not followup:
        raise HTTPException(404, "Follow-up not found")
    followup.isActive = False
    followup.lastupdateby = ctx.user_id
    followup.lastupdateon = now_ist()
    db.commit()
    return {"message": "Follow-up deleted"}
