import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func
from typing import List, Optional

from pydantic import BaseModel
from app.core.timezone import now_ist
from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.pagination import PaginationParams, paginate
from app.core.cursor_pagination import CursorParams, cursor_paginate
from app.models.quotation import QuotSummary, QuotDetails, QuotTermsNConditions, QuotFollowUp
from app.models.enquiry import CustomerEnquiry, CustomerEnquiryDetails, CustomerEnquiryCosting
from app.models.financial_year import FinancialYear
from app.models.terms_condition import TermsNConditionMaster
from app.models.user import User, UserRoleMap
from app.models.company import Company
from app.services.quotation_service import COST_HEAD_COLS
from app.services.costing_service import get_tp_cost_for_dia
from app.services.activity_log_service import log_action, log_failure
from app.schemas.quotation import (
    QuotSummaryCreate, QuotSummaryUpdate, QuotSummaryResponse,
    QuotDetailCreate, QuotDetailResponse,
    QuotTncCreate, QuotTncResponse, QuotTncReorderItem,
    QuotFollowUpCreate, QuotFollowUpResponse,
)
from app.schemas.quot_purchase_order import (
    QuotPurchaseOrderBody, QuotPurchaseOrderResponse, UnlockEditBody,
    StageVersionListItem,
)
from app.services import viability_service, annexure_service
from app.schemas.quot_po_working_sheet import (
    QuotPOWorkingSheetLineBody, QuotPOWorkingSheetLineResponse,
)
from app.models.customer import CustomerSite
from app.services.quotation_service import create_quotation_revision
from app.services import purchase_order_service, lifecycle_service, po_working_sheet_service
from app.models.quot_purchase_order import QuotPurchaseOrder
from app.models.quot_viability import QuotViabilitySheet
from app.models.quot_annexure import QuotAnnexure
from app.services.access_service import (
    AccessContext, get_access_context,
    apply_company_filter, apply_hierarchy_filter, apply_location_filter,
    require_permission, require_owner_visible, require_location_access,
    require_parent_visible,
)

MENU = "Quotations"

router = APIRouter()


# ===== Search (cursor-based, for dropdown lookups) =====

@router.get("/search")
def search_quotations(
    enqId: Optional[int] = Query(None, description="Restrict to quotations linked to this enquiry"),
    params: CursorParams = Depends(),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Cursor-paginated quotation search for dropdowns. Scales to 50k+ rows.

    - Prefix/substring match on quotNo and subject
    - Applies F2/F5/F6 visibility (company + hierarchy + location)
    - Returns latest first (descending quotId)
    - Optional ``enqId`` filter scopes results to a single enquiry's
      quotations — used by the communication-log dialog to enforce
      that the picked quotation actually belongs to the picked enquiry.
    """
    require_permission(MENU, "CanRead", ctx)
    from app.models.customer import CustomerMaster

    q = db.query(
        QuotSummary.quotId,
        QuotSummary.quotNo,
        QuotSummary.subject,
        QuotSummary.quotDate,
        QuotSummary.status,
        QuotSummary.customerId,
        CustomerMaster.customerName,
    ).join(
        CustomerMaster, QuotSummary.customerId == CustomerMaster.customerId,
    ).outerjoin(
        CustomerSite, QuotSummary.siteId == CustomerSite.siteId,
    ).filter(QuotSummary.isActive == True)
    q = apply_company_filter(q, QuotSummary.companyId, ctx)
    q = apply_hierarchy_filter(q, QuotSummary.ownerUserId, ctx)
    q = apply_location_filter(
        q, CustomerSite.state, CustomerSite.dist, ctx,
        nullable_fk=QuotSummary.siteId,
    )
    if enqId is not None:
        q = q.filter(QuotSummary.enqid == enqId)

    # id-lookup mode
    if params.ids:
        rows = q.filter(QuotSummary.quotId.in_(params.ids)).all()
        return {
            "items": [
                {
                    "id": r.quotId, "label": r.quotNo, "sub": r.subject or r.customerName,
                    "quotDate": r.quotDate, "status": r.status,
                    "customerId": r.customerId, "customerName": r.customerName,
                }
                for r in rows
            ],
            "nextCursor": None, "hasMore": False,
        }

    if params.q:
        term = f"%{params.q}%"
        q = q.filter(
            (QuotSummary.quotNo.ilike(term))
            | (QuotSummary.subject.ilike(term))
        )

    rows, next_cursor, has_more = cursor_paginate(
        q, QuotSummary.quotId, params, descending=True,
    )
    return {
        "items": [
            {
                "id": r.quotId,
                "label": r.quotNo,
                "sub": r.subject or r.customerName,
                "quotDate": r.quotDate,
                "status": r.status,
                "customerId": r.customerId,
                "customerName": r.customerName,
            }
            for r in rows
        ],
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


# ===== Quotation Summary =====

@router.get("")
def get_quotations(
    customerId: Optional[int] = Query(None),
    dateFrom: Optional[str] = Query(None),
    dateTo: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    q = db.query(QuotSummary).options(
        joinedload(QuotSummary.customer),
    ).outerjoin(
        CustomerSite, QuotSummary.siteId == CustomerSite.siteId,
    ).filter(QuotSummary.isActive == True)
    q = apply_company_filter(q, QuotSummary.companyId, ctx)
    q = apply_hierarchy_filter(q, QuotSummary.ownerUserId, ctx)
    q = apply_location_filter(q, CustomerSite.state, CustomerSite.dist, ctx,
                              nullable_fk=QuotSummary.siteId)
    if customerId:
        q = q.filter(QuotSummary.customerId == customerId)
    if dateFrom:
        q = q.filter(QuotSummary.quotDate >= dateFrom)
    if dateTo:
        q = q.filter(QuotSummary.quotDate <= dateTo)
    if status:
        q = q.filter(QuotSummary.status == status)
    if pagination.search:
        q = q.filter(
            (QuotSummary.quotNo.ilike(f"%{pagination.search}%")) |
            (QuotSummary.subject.ilike(f"%{pagination.search}%"))
        )

    # Sorting — whitelist prevents `?sortBy=…` from resolving to arbitrary
    # model attributes. Additions here require an explicit code change.
    from app.core.pagination import resolve_sort_column
    _ALLOWED_QUOT_SORT = {
        "quotId",           # default list sort (desc)
        "quotNo", "quotDate", "subject", "status",
        "versionNo", "revisionNo", "createdon", "lastupdateon",
    }
    sort_col = resolve_sort_column(
        QuotSummary, pagination.sort_by, allowed=_ALLOWED_QUOT_SORT,
    )
    if sort_col is not None:
        q = q.order_by(sort_col.desc() if pagination.sort_dir == "desc" else sort_col.asc())
    else:
        q = q.order_by(QuotSummary.quotId.desc())

    result = paginate(q, pagination)
    # Attach customerName from joined relationship
    result["items"] = [
        {
            **{c.key: getattr(row, c.key) for c in row.__table__.columns},
            "customerName": row.customer.customerName if row.customer else None,
        }
        for row in result["items"]
    ]
    return result


@router.get("/search-for-tnc")
def search_quotations_for_tnc(
    q: str = Query("", description="Search by quotNo or customer name"),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Search quotations for TnC import — lightweight results."""
    require_permission(MENU, "CanRead", ctx)
    from app.models.customer import CustomerMaster
    if not q or len(q) < 2:
        return []
    query = (
        db.query(QuotSummary.quotId, QuotSummary.quotNo, QuotSummary.quotDate, CustomerMaster.customerName)
        .join(CustomerMaster, QuotSummary.customerId == CustomerMaster.customerId)
        .filter(
            QuotSummary.isActive == True,
            (QuotSummary.quotNo.ilike(f"%{q}%")) | (CustomerMaster.customerName.ilike(f"%{q}%")),
        )
    )
    query = apply_company_filter(query, QuotSummary.companyId, ctx)
    query = apply_hierarchy_filter(query, QuotSummary.ownerUserId, ctx)
    results = query.order_by(QuotSummary.quotId.desc()).limit(20).all()
    return [{"quotId": r.quotId, "quotNo": r.quotNo, "quotDate": r.quotDate, "customerName": r.customerName} for r in results]


@router.get("/tnc-master/{tnc_id}")
def get_master_tnc(
    tnc_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Fetch a master T&C by its ID to refresh a quotation row."""
    master = db.query(TermsNConditionMaster).filter(
        TermsNConditionMaster.tncId == tnc_id,
        TermsNConditionMaster.companyId == ctx.company_id,
        TermsNConditionMaster.isActive == True,
    ).first()
    if not master:
        raise HTTPException(status_code=404, detail="Master term not found")
    return {"tncId": master.tncId, "tncName": master.tncName, "tncDescription": master.tncDescription}


@router.get("/{quot_id}/print-data")
def get_quotation_print_data(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Returns quotation with joined customer, contact, site, delivery term/mode for print."""
    require_permission(MENU, "CanRead", ctx)
    q = db.query(QuotSummary).options(
        joinedload(QuotSummary.customer),
        joinedload(QuotSummary.contact),
        joinedload(QuotSummary.site),
        joinedload(QuotSummary.delivery_term),
        joinedload(QuotSummary.delivery_mode),
        joinedload(QuotSummary.owner),
    ).outerjoin(
        CustomerSite, QuotSummary.siteId == CustomerSite.siteId,
    ).filter(
        QuotSummary.quotId == quot_id,
        QuotSummary.isActive == True,
    )
    q = apply_company_filter(q, QuotSummary.companyId, ctx)
    q = apply_hierarchy_filter(q, QuotSummary.ownerUserId, ctx)
    q = apply_location_filter(q, CustomerSite.state, CustomerSite.dist, ctx,
                              nullable_fk=QuotSummary.siteId)
    quot = q.first()
    if not quot:
        raise HTTPException(status_code=404, detail="Quotation not found")

    company_obj = db.query(Company).filter(Company.companyId == ctx.company_id).first()

    # Resolve owner: prefer ownerUserId relationship, fallback to parsing userCode from quotNo
    owner = quot.owner
    if not owner and quot.quotNo:
        # quotNo format: QUOT-{userCode}-{fyCode}-{serial}[-R{n}]
        parts = (quot.quotNo or "").split("-")
        if len(parts) >= 2:
            parsed_code = parts[1]  # e.g. "0116"
            owner = db.query(User).filter(
                User.userCode == parsed_code,
                User.isActive == True,
            ).first()

    # Find customer's Head Office site
    ho_site = None
    if quot.customer:
        ho_site = db.query(CustomerSite).filter(
            CustomerSite.customerId == quot.customer.customerId,
            CustomerSite.isHeadOffice == True,
            CustomerSite.isActive == True,
        ).first()

    contact = quot.contact
    customer = quot.customer

    return {
        "quotId": quot.quotId,
        "quotNo": quot.quotNo,
        "quotDate": quot.quotDate,
        "subject": quot.subject,
        "versionNo": quot.versionNo,
        "status": quot.status,
        "refQuotNo": quot.refQuotNo,
        # PO no/date moved to QuotPurchaseOrder; surface them here from
        # the linked PO so the print payload stays backward-compatible
        # with the consumer template (None until PO is captured).
        "CustomerPONo": quot.purchase_order.poNo if quot.purchase_order else None,
        "CustomerPODate": quot.purchase_order.poDate if quot.purchase_order else None,
        "remarks": quot.remarks,
        # Customer details
        "customerName": customer.customerName if customer else None,
        "customerCode": customer.customerCode if customer else None,
        "customerGSTN": customer.GSTN if customer else None,
        "customerPAN": customer.PAN if customer else None,
        # Customer HO (from site with isHeadOffice=True)
        "customerHOAddress": _build_site_address(ho_site) if ho_site else "",
        "customerHOSiteCode": ho_site.siteAddressCode if ho_site else None,
        # Selected contact person
        "contactName": contact.contactPersonName if contact else None,
        "contactDesignation": contact.designation if contact else None,
        "contactPhone": (contact.officePhone or contact.personalPhone) if contact else None,
        "contactEmail": (contact.officeEmail or contact.personalEmail) if contact else None,
        "contactAddress": contact.address if contact else None,
        # Delivery site
        "siteName": quot.site.siteAddressCode if quot.site else None,
        "siteAddress": _build_site_address(quot.site) if quot.site else None,
        # Delivery
        "deliveryTerm": quot.delivery_term.deliveryTerm if quot.delivery_term else None,
        "deliveryMode": quot.delivery_mode.deliveryMode if quot.delivery_mode else None,
        # Owner (person whose userCode is in the quotation number)
        "ownerName": owner.userName if owner else None,
        "ownerCode": owner.userCode if owner else None,
        "ownerEmail": owner.userEmail if owner else None,
        "ownerPhone": owner.userPhone if owner else None,
        "ownerDesignation": owner.userDesignation if owner else None,
        # Company details from session
        "companyName": company_obj.companyName if company_obj else None,
        "companyAddress": _build_company_address(company_obj),
        "companyGSTN": company_obj.GSTN if company_obj else None,
        "companyPhone": company_obj.phone if company_obj else None,
        "companyEmail": company_obj.email if company_obj else None,
        "companyWebsite": company_obj.website if company_obj else None,
        "companyPAN": company_obj.PAN if company_obj else None,
        "companyLogoUrl": company_obj.logoUrl if company_obj else None,
    }


def _build_site_address(site) -> str:
    """Build address string from a CustomerSite."""
    if not site:
        return ""
    parts = [p for p in [site.addressLine, site.dist, site.state, site.PIN] if p]
    return ", ".join(parts)


def _build_company_address(company) -> str:
    """Build company address from address, city, state, pinCode."""
    if not company:
        return ""
    parts = [p for p in [company.address, company.city, company.state, company.pinCode] if p]
    return ", ".join(parts)


def _get_quot_or_403(db: Session, quot_id: int, ctx: AccessContext) -> QuotSummary:
    """Fetch quotation with F2/F5/F6 checks. Raises 404/403.

    Eager-loads ``purchase_order`` and its nested customer / contact /
    billing_site / consignee_site so the response serializer can resolve
    the denormalised labels (customerName, contactPersonName,
    billing/consigneeSiteAddress) without N+1 lazy queries — and so
    Pydantic's ``from_attributes`` walk doesn't blow up after the
    session closes.
    """
    from app.models.quot_purchase_order import QuotPurchaseOrder
    q = db.query(QuotSummary).options(
        selectinload(QuotSummary.purchase_order).options(
            selectinload(QuotPurchaseOrder.customer),
            selectinload(QuotPurchaseOrder.contact),
            selectinload(QuotPurchaseOrder.billing_site),
            selectinload(QuotPurchaseOrder.consignee_site),
        ),
    ).outerjoin(
        CustomerSite, QuotSummary.siteId == CustomerSite.siteId,
    ).filter(
        QuotSummary.quotId == quot_id,
        QuotSummary.isActive == True,
    )
    q = apply_company_filter(q, QuotSummary.companyId, ctx)
    q = apply_hierarchy_filter(q, QuotSummary.ownerUserId, ctx)
    q = apply_location_filter(q, CustomerSite.state, CustomerSite.dist, ctx,
                              nullable_fk=QuotSummary.siteId)
    quot = q.first()
    if not quot:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return quot


@router.get("/{quot_id}", response_model=QuotSummaryResponse)
def get_quotation(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    return _get_quot_or_403(db, quot_id, ctx)


@router.post("", response_model=QuotSummaryResponse, status_code=201)
def create_quotation(
    data: QuotSummaryCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
    current_user: CurrentUser = Depends(get_current_user),
):
    require_permission(MENU, "CanAdd", ctx)
    from app.services.owner_resolver import resolve_owner

    # F6: Validate site location access
    if data.siteId:
        site = db.query(CustomerSite).filter(CustomerSite.siteId == data.siteId).first()
        if site:
            require_location_access(
                site.state, site.dist, ctx,
                detail="You do not have access to this site's location",
            )

    data_dict = data.model_dump()
    code_user_id = data_dict.pop("codeUserId", None)

    # Select-code mode requires CanGenerateUnderOthers permission
    if code_user_id and ctx.role and ctx.role.numGenMode == "select_code":
        if not ctx.has_permission(MENU, "CanGenerateUnderOthers"):
            raise HTTPException(
                403, "You do not have permission to generate numbers under other users",
            )

    owner = resolve_owner(db, current_user, code_user_id)

    user_supplied_quot_no = data_dict.get("quotNo")
    # Manual override of the auto-generated FY-scoped quotation number is
    # a privileged action — it bypasses the serial allocator and lets the
    # caller pick any string, which is sensitive for audit and number-
    # sequence integrity. ``CanEditNumber`` is the dedicated gate.
    # Migration ``v3w4x5y6z7a8`` backfills it from ``CanAdd`` so existing
    # roles that today rely on the (previously ungated) override keep
    # working; admins can subsequently revoke it for stricter control.
    if user_supplied_quot_no and not ctx.has_permission(MENU, "CanEditNumber"):
        raise HTTPException(
            403,
            "You do not have permission to override the auto-generated quotation number.",
        )
    fy_code: Optional[str] = None
    if not user_supplied_quot_no:
        fy = db.query(FinancialYear).filter(
            FinancialYear.companyId == ctx.company_id,
            FinancialYear.isCurrent == True,
            FinancialYear.isActive == True,
        ).first()
        if not fy:
            raise HTTPException(400, "No current Financial Year set for this company")
        fy_code = fy.fyCode

    def _next_quot_no() -> str:
        # User-supplied case: no retry pool — same number every attempt, so a
        # collision raises 409 and the user adjusts. Auto-gen case: re-count
        # inside the loop so concurrent inserts bump the candidate forward.
        if user_supplied_quot_no:
            return user_supplied_quot_no
        count = db.query(func.count(QuotSummary.quotId)).filter(
            QuotSummary.companyId == ctx.company_id,
            QuotSummary.quotNo.like(f"QUOT-%-{fy_code}-%"),
        ).scalar() or 0
        return f"QUOT-{owner['userCode']}-{fy_code}-{count + 1:04d}"

    def _build_quot(quot_no: str) -> QuotSummary:
        # Fresh instance per attempt — rollback detaches the previous one.
        return QuotSummary(
            **{**data_dict, "quotNo": quot_no},
            companyId=ctx.company_id,
            ownerUserId=owner["userId"],
            ownerRoleId=owner["roleId"],
            versionNo=1,
            status="Draft",
            createdby=ctx.user_id,
        )

    from app.services.number_allocator import allocate_and_flush
    # C2: serialize auto-gen allocation per (company, owner-userCode, fy) so
    # parallel "create quotation" calls can't read the same MAX() and
    # collide. User-supplied numbers stay on the old optimistic path —
    # there's no count to race on, the unique index just bounces dupes.
    _alloc_lock_key = (
        None if user_supplied_quot_no
        else f"NUM:QUOT:{ctx.company_id}:{owner['userCode']}:{fy_code}"
    )
    quot = allocate_and_flush(
        db,
        build=_build_quot,
        compute_number=_next_quot_no,
        max_attempts=1 if user_supplied_quot_no else 10,
        lock_key=_alloc_lock_key,
        conflict_message=(
            "Quotation number already exists — choose a different one."
            if user_supplied_quot_no
            else "Could not allocate a unique quotation number after retries."
        ),
    )

    # Lock the source enquiry when a quotation is created from it
    if data_dict.get("enqid"):
        enq = db.query(CustomerEnquiry).filter(
            CustomerEnquiry.enqid == data_dict["enqid"],
            CustomerEnquiry.companyId == ctx.company_id,
            CustomerEnquiry.isActive == True,
        ).first()
        if enq and enq.status not in ("Quotation Prepared", "Reject"):
            enq.status = "Quotation Prepared"
            enq.lastupdateby = ctx.user_id

    log_action(db, quot_id=quot.quotId, company_id=quot.companyId,
               action="Created", status=quot.status or "Draft", user_id=ctx.user_id,
               details=f"Quotation {quot.quotNo}" if quot.quotNo else None)
    db.commit()
    db.refresh(quot)
    return quot


@router.put("/{quot_id}", response_model=QuotSummaryResponse)
def update_quotation(
    quot_id: int,
    data: QuotSummaryUpdate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    quot = _get_quot_or_403(db, quot_id, ctx)
    # Revised quotations are fully locked
    if quot.status == "Revised":
        raise HTTPException(400, "Cannot edit a Revised quotation")
    # Converted quotations — generic editing is no longer supported
    # through this endpoint. PO header changes (the only thing that
    # used to be legal here) now go through
    # PUT /quotations/{id}/purchase-order so the audit trail and the
    # locking rule live in one place. Stage-1 amendments after Convert
    # use the privileged Unlock-and-Edit path.
    if quot.status == "Converted":
        raise HTTPException(
            400,
            "Quotation is Converted. Edit the captured PO via "
            "PUT /quotations/{id}/purchase-order, or use the privileged "
            "Unlock-and-Edit action to amend Stage-1 fields.",
        )
    changed_fields: list[str] = []
    for k, v in data.model_dump(exclude_unset=True).items():
        if getattr(quot, k, None) != v:
            changed_fields.append(k)
        setattr(quot, k, v)
    quot.lastupdateby = ctx.user_id
    if changed_fields:
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="Quotation updated", status=quot.status, user_id=ctx.user_id,
            details=f"fields: {', '.join(changed_fields)}",
        )
    db.commit()
    db.refresh(quot)
    return quot


@router.delete("/{quot_id}", status_code=204)
def delete_quotation(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanDelete", ctx)
    quot = _get_quot_or_403(db, quot_id, ctx)
    quot.isActive = False
    quot.lastupdateby = ctx.user_id
    db.commit()


# ===== Ownership Handover =====

class QuotHandoverRequest(BaseModel):
    targetUserId: int
    remarks: Optional[str] = None


@router.post("/{quot_id}/handover")
def handover_quotation(
    quot_id: int,
    payload: QuotHandoverRequest,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Transfer quotation ownership. Reopens (status=Draft) if previously approved.
    Requires CanTransferOwnership. Target must be visible to initiator.
    """
    try:
        require_permission(MENU, "CanTransferOwnership", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)

        # Target must be visible to initiator
        require_owner_visible(payload.targetUserId, ctx)

        target_user = db.query(User).filter(
            User.userId == payload.targetUserId,
            User.companyId == ctx.company_id,
            User.isActive == True,
        ).first()
        if not target_user:
            raise HTTPException(404, "Target user not found in company")

        urm = db.query(UserRoleMap).filter(
            UserRoleMap.userId == target_user.userId,
            UserRoleMap.companyId == ctx.company_id,
            UserRoleMap.isActive == True,
        ).first()

        prior_approvedby = quot.approvedby
        prior_approvedon = quot.approvedon
        prior_owner_id = quot.ownerUserId

        quot.ownerUserId = target_user.userId
        quot.ownerRoleId = urm.roleId if urm else None
        # Reopen if approved — fresh owner reviews before re-approving.
        # Before clearing approvedby/on, write an archival activity-log row
        # so the timeline retains who approved and when.
        approval_reset = False
        if quot.status == "Approved":
            if prior_approvedby is not None or prior_approvedon is not None:
                log_action(
                    db, quot_id=quot.quotId, company_id=quot.companyId,
                    action="Approval cleared by handover", status="Approved",
                    user_id=ctx.user_id,
                    details=(
                        f"previous approver={prior_approvedby}, "
                        f"approvedon={prior_approvedon}"
                    ),
                )
            quot.status = "Draft"
            quot.approvedby = None
            quot.approvedon = None
            approval_reset = True
        quot.lastupdateby = ctx.user_id
        quot.lastupdateon = now_ist()
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="Ownership Handed Over", status=quot.status, user_id=ctx.user_id,
            details=(
                f"fromUserId={prior_owner_id} → toUserId={target_user.userId} "
                f"({target_user.userName})"
                + ("; reopened to Draft" if approval_reset else "")
            ),
        )
        db.commit()
        db.refresh(quot)
        return {
            "message": "Quotation ownership transferred",
            "quotId": quot.quotId,
            "newOwnerUserId": quot.ownerUserId,
            "status": quot.status,
        }
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Handover", user_id=ctx.user_id, exc=e)
        raise


# --- Activity Log ---

@router.get("/{quot_id}/activity-log")
def get_activity_log(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Timewise log of lifecycle actions for this quotation, newest first.
    Access is gated by the standard quotation read rules."""
    require_permission(MENU, "CanRead", ctx)
    _get_quot_or_403(db, quot_id, ctx)
    from app.models.quot_activity_log import QuotActivityLog
    rows = (
        db.query(QuotActivityLog)
        .filter(QuotActivityLog.quotId == quot_id)
        .order_by(QuotActivityLog.actionOn.desc(), QuotActivityLog.logId.desc())
        .all()
    )
    return [
        {
            "logId": r.logId,
            "action": r.action,
            "status": r.status,
            "outcome": getattr(r, "outcome", "Success"),
            "details": r.details,
            "actionOn": r.actionOn,
            "actionByUserId": r.actionByUserId,
            "actionByName": r.actionByName,
        }
        for r in rows
    ]


# --- Versioning ---

@router.post("/{quot_id}/revise", response_model=QuotSummaryResponse)
def revise_quotation(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    try:
        require_permission(MENU, "CanRevise", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        if quot.status != "Approved":
            raise HTTPException(400, f"Only Approved quotations can be revised (current: {quot.status})")
        new_quot = create_quotation_revision(
            db, quot_id, ctx.company_id, ctx.user_id,
        )
        # Log on the original (now 'Revised') and the new version (a fresh 'Draft').
        log_action(db, quot_id=quot.quotId, company_id=quot.companyId,
                   action="Revised (superseded)", status=quot.status, user_id=ctx.user_id,
                   details=f"New version created: quotId={new_quot.quotId}, v{new_quot.versionNo}")
        log_action(db, quot_id=new_quot.quotId, company_id=new_quot.companyId,
                   action="Created (revision)", status=new_quot.status or "Draft", user_id=ctx.user_id,
                   details=f"Revision of quotId={quot.quotId} (v{quot.versionNo})")
        db.commit()
        db.refresh(new_quot)
        return new_quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Revise", user_id=ctx.user_id, exc=e)
        raise


@router.get("/{quot_id}/versions", response_model=List[QuotSummaryResponse])
def get_quotation_versions(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    # Run the entry quotation through the same F2/F5/F6 pipeline the rest of
    # the router uses — without it a caller could probe `parentQuotId` for
    # any quotation in the database and learn revision-chain anchors across
    # tenants. (Was: bare `db.query(QuotSummary).filter(quotId == quot_id)`.)
    quot = _get_quot_or_403(db, quot_id, ctx)
    parent_id = quot.parentQuotId or quot.quotId
    # Eager-load ``purchase_order`` plus its nested customer / contact
    # / sites — the response shape now carries denormalised labels
    # resolved from those relationships, so without the chain every
    # version row triggers an N+1 storm during Pydantic serialization.
    from app.models.quot_purchase_order import QuotPurchaseOrder
    q = db.query(QuotSummary).options(
        selectinload(QuotSummary.purchase_order).options(
            selectinload(QuotPurchaseOrder.customer),
            selectinload(QuotPurchaseOrder.contact),
            selectinload(QuotPurchaseOrder.billing_site),
            selectinload(QuotPurchaseOrder.consignee_site),
        ),
    ).filter(
        (QuotSummary.parentQuotId == parent_id) | (QuotSummary.quotId == parent_id),
        QuotSummary.isActive == True,
    )
    q = apply_company_filter(q, QuotSummary.companyId, ctx)
    q = apply_hierarchy_filter(q, QuotSummary.ownerUserId, ctx)
    return q.order_by(QuotSummary.versionNo.desc()).all()


# --- Approval ---

@router.put("/{quot_id}/approve", response_model=QuotSummaryResponse)
def approve_quotation(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    try:
        require_permission(MENU, "CanApprove", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)

        # State-machine guard: approve only valid from Draft. Previously any
        # status (Matured, Reject, Revised, Viability*, Annexure*) could be
        # re-approved, corrupting the approval audit trail and letting a
        # rejected quotation return to Approved by bypassing revert-reject.
        if quot.status != "Draft":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Only Draft quotations can be approved "
                    f"(current: {quot.status}). Use /revert-reject to unwind a rejected quotation."
                ),
            )

        # Completeness validation — a quotation can't be approved unless it
        # has the minimum content the document is meaningless without. Catch
        # this server-side so the rule holds even if a client bypasses the UI.
        details_count = db.query(func.count(QuotDetails.quotDtlId)).filter(
            QuotDetails.quotId == quot.quotId,
            QuotDetails.isActive == True,
        ).scalar() or 0
        tnc_count = db.query(func.count(QuotTermsNConditions.quotTncId)).filter(
            QuotTermsNConditions.quotId == quot.quotId,
            QuotTermsNConditions.isActive == True,
        ).scalar() or 0

        missing: List[str] = []
        if details_count == 0:
            missing.append("at least one line item")
        if tnc_count == 0:
            missing.append("at least one Terms & Conditions entry")
        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot approve — quotation is missing "
                    + " and ".join(missing)
                    + ". Add the required content first."
                ),
            )

        # Delivery term itself must be set on a quotation we're approving —
        # the freight rule below depends on it, and a quotation without a
        # term is structurally incomplete.
        if not quot.deliveryTermId:
            raise HTTPException(
                status_code=400,
                detail="Cannot approve — Delivery Term is required.",
            )

        # FOR delivery → the freight column matching the chosen Delivery
        # Mode must be filled on every line. Non-FOR terms skip this check
        # since freight is informational there.
        if _is_for_delivery_term(quot):
            mode = _delivery_mode_name(quot)
            if not mode:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Cannot approve — Delivery Term is FOR but Delivery "
                        "Mode is not set. Choose Trailer or Truck so the "
                        "matching freight column is locked in."
                    ),
                )
            if _mode_is_trailer(mode):
                target_col = QuotDetails.FreightTrailer
                col_label = "Freight (Trailer)"
            elif _mode_is_truck(mode):
                target_col = QuotDetails.FreightTruck
                col_label = "Freight (Truck)"
            else:
                target_col = None
                col_label = ""
            if target_col is not None:
                lines_without_freight = db.query(QuotDetails).filter(
                    QuotDetails.quotId == quot.quotId,
                    QuotDetails.isActive == True,
                    ((target_col.is_(None)) | (target_col == 0)),
                ).count()
                if lines_without_freight:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Cannot approve — delivery term is FOR with mode "
                            f"'{quot.delivery_mode.deliveryMode}' and "
                            f"{lines_without_freight} line item(s) have no "
                            f"{col_label} value. Enter {col_label} on every line."
                        ),
                    )

        quot.approvedby = ctx.user_id
        quot.approvedon = now_ist()
        quot.status = "Approved"
        quot.lastupdateby = ctx.user_id
        log_action(db, quot_id=quot.quotId, company_id=quot.companyId,
                   action="Approved", status=quot.status, user_id=ctx.user_id)
        db.commit()
        db.refresh(quot)
        return quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Approve", user_id=ctx.user_id, exc=e)
        raise


@router.put("/{quot_id}/mature", response_model=QuotSummaryResponse)
def mature_quotation(
    quot_id: int,
    body: QuotPurchaseOrderBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Capture the customer Purchase Order and transition Approved →
    Matured atomically.

    The body is the PO header the customer actually sent in: PO No,
    PO Date, customer + contact (defaulted to the quotation's, but
    overridable for group-company billing), and billing + consignee
    addresses. For each address pair the body must populate exactly
    one of (siteId, addressManual) — see ``purchase_order_service``.
    """
    try:
        require_permission(MENU, "CanApprove", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        if quot.status != "Approved":
            raise HTTPException(
                400,
                f"Only Approved quotations can be matured (current: {quot.status})",
            )
        try:
            po = purchase_order_service.create_or_update_po(
                db, quot, body, user_id=ctx.user_id,
            )
        except purchase_order_service.PurchaseOrderValidationError as exc:
            raise HTTPException(400, str(exc))

        # Phase-1 semantics: ``Matured`` collapsed into ``Converted`` on
        # the quotation, AND the PO row goes straight to ``Submitted``
        # because legacy /mature callers expected single-step capture.
        # New callers should use /convert + /purchase-order/submit for
        # the explicit two-step flow.
        po.status = "Submitted"
        po.sourcedFromQuotationVersion = quot.versionNo  # Phase 3 freshness
        quot.status = "Converted"
        quot.convertedOn = now_ist()
        quot.convertedBy = ctx.user_id
        quot.lastupdateby = ctx.user_id
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="Converted (PO Submitted)", status=quot.status,
            user_id=ctx.user_id,
            details=f"PO {po.poNo} dated {po.poDate}",
        )
        db.commit()
        db.refresh(quot)
        return quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Mature", user_id=ctx.user_id, exc=e)
        raise


@router.get(
    "/{quot_id}/purchase-order",
    response_model=Optional[QuotPurchaseOrderResponse],
)
def get_purchase_order(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Fetch the active PO for a quotation, or null when one hasn't been
    captured yet (e.g. quotation still in Draft / Approved)."""
    require_permission(MENU, "CanRead", ctx)
    quot = _get_quot_or_403(db, quot_id, ctx)
    return purchase_order_service.get_po(db, quot)


@router.put("/{quot_id}/purchase-order", response_model=QuotPurchaseOrderResponse)
def update_purchase_order(
    quot_id: int,
    body: QuotPurchaseOrderBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Edit a PO that was already captured. Allowed only while the
    quotation is in Matured status — once viability work begins
    (status = ViabilityGenerated or later) the PO is locked so the
    downstream artifacts can't drift from the source they were
    generated against. 409 in that case."""
    try:
        require_permission(MENU, "CanApprove", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        try:
            purchase_order_service.ensure_editable(quot)
        except purchase_order_service.PurchaseOrderConflictError as exc:
            raise HTTPException(409, str(exc))
        try:
            po = purchase_order_service.create_or_update_po(
                db, quot, body, user_id=ctx.user_id,
            )
        except purchase_order_service.PurchaseOrderValidationError as exc:
            raise HTTPException(400, str(exc))
        quot.lastupdateby = ctx.user_id
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="PO Updated", status=quot.status, user_id=ctx.user_id,
            details=f"PO {po.poNo} dated {po.poDate}",
        )
        db.commit()
        db.refresh(po)
        return po
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="PO Update", user_id=ctx.user_id, exc=e)
        raise


@router.put("/{quot_id}/reject", response_model=QuotSummaryResponse)
def reject_quotation(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Reject a quotation. Only Approved quotations can be rejected."""
    try:
        require_permission(MENU, "CanApprove", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        if quot.status != "Approved":
            raise HTTPException(400, f"Only Approved quotations can be rejected (current: {quot.status})")
        quot.status = "Reject"
        quot.lastupdateby = ctx.user_id
        log_action(db, quot_id=quot.quotId, company_id=quot.companyId,
                   action="Rejected", status=quot.status, user_id=ctx.user_id)
        db.commit()
        db.refresh(quot)
        return quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Reject", user_id=ctx.user_id, exc=e)
        raise


@router.put("/{quot_id}/revert-reject", response_model=QuotSummaryResponse)
def revert_reject_quotation_legacy(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Phase-4 sunset: ``/revert-reject`` is now an alias for the
    canonical ``/reactivate`` endpoint. Frontend has been on the new
    name since Phase 1; this stub preserves the URL for any external
    integration still pointing at it. Will be removed in a follow-up
    release after a deprecation window."""
    return reactivate_quotation(quot_id, db=db, ctx=ctx)


# ---------------------------------------------------------------------------
# Phase 1 lifecycle transitions: Convert, Reactivate, PO Submit/Reject,
# generic per-stage Unlock-and-Edit
# ---------------------------------------------------------------------------

@router.put("/{quot_id}/convert", response_model=QuotSummaryResponse)
def convert_quotation(
    quot_id: int,
    body: QuotPurchaseOrderBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Stage-1 forward gate: ``Approved → Converted``.

    Captures the customer PO atomically with the status transition
    (same body shape as legacy /mature), but leaves the PO row in
    ``Draft`` so the user can fill in the Final Working Sheet (Phase
    1.5) before firing /purchase-order/submit.
    """
    try:
        require_permission(MENU, "CanConvert", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        if quot.status != "Approved":
            raise HTTPException(
                400,
                f"Only Approved quotations can be Converted (current: {quot.status})",
            )
        try:
            po = purchase_order_service.create_or_update_po(
                db, quot, body, user_id=ctx.user_id,
            )
        except purchase_order_service.PurchaseOrderValidationError as exc:
            raise HTTPException(400, str(exc))

        po.status = "Draft"
        # Phase 3 freshness pointer — record which quotation version
        # this PO was Converted from. The frontend compares this to
        # the current quotation head to surface a stale banner if the
        # quotation is later Revised.
        po.sourcedFromQuotationVersion = quot.versionNo
        quot.status = "Converted"
        quot.convertedOn = now_ist()
        quot.convertedBy = ctx.user_id
        quot.lastupdateby = ctx.user_id
        # Clone the quotation's Working Sheet into the PO's Final
        # Working Sheet so the user can immediately tweak qty / cost
        # heads on the Stage-2 grid. Idempotent on re-Convert (e.g.
        # after a Reject) — preserves any in-flight edits.
        cloned = po_working_sheet_service.clone_from_quotation(
            db, po, quot, user_id=ctx.user_id,
        )
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="Converted", status=quot.status, user_id=ctx.user_id,
            details=f"PO {po.poNo} dated {po.poDate} · {len(cloned)} working-sheet lines cloned",
        )
        db.commit()
        db.refresh(quot)
        return quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Convert", user_id=ctx.user_id, exc=e)
        raise


@router.put("/{quot_id}/reactivate", response_model=QuotSummaryResponse)
def reactivate_quotation(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Reactivate a Rejected quotation back to Approved.

    Replaces the legacy /revert-reject with a clearer name and the
    new ``CanReactivate`` permission. /revert-reject stays as an
    alias for backward compat for one release.
    """
    try:
        require_permission(MENU, "CanReactivate", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        if quot.status != "Reject":
            raise HTTPException(
                400, f"Only Rejected quotations can be reactivated (current: {quot.status})",
            )
        if quot.approvedby is None:
            quot.approvedby = ctx.user_id
            quot.approvedon = now_ist()
        quot.status = "Approved"
        quot.lastupdateby = ctx.user_id
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="Reactivated", status=quot.status, user_id=ctx.user_id,
        )
        db.commit()
        db.refresh(quot)
        return quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="Reactivate", user_id=ctx.user_id, exc=e)
        raise


@router.put("/{quot_id}/purchase-order/submit", response_model=QuotPurchaseOrderResponse)
def submit_purchase_order(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Stage-2 forward gate: PO ``Draft → Submitted``. Quotation
    stays at ``Converted`` (Stage-2 internal state)."""
    try:
        require_permission(MENU, "CanSubmitPO", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        if quot.status != "Converted":
            raise HTTPException(
                400, f"PO can only be submitted while the quotation is Converted (current: {quot.status})",
            )
        try:
            po = purchase_order_service.submit_po(db, quot, user_id=ctx.user_id)
        except purchase_order_service.PurchaseOrderConflictError as exc:
            raise HTTPException(409, str(exc))
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="PO Submitted & Matured", status=quot.status,
            user_id=ctx.user_id,
            details=f"PO {po.poNo} v{po.versionNo}",
        )
        db.commit()
        db.refresh(po)
        return po
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="PO Submit", user_id=ctx.user_id, exc=e)
        raise


@router.put("/{quot_id}/purchase-order/reject", response_model=QuotSummaryResponse)
def reject_purchase_order(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Stage-2 backward escape: PO ``Submitted → Rejected``, AND
    quotation un-Converts back to ``Approved`` so the user can
    Revise / re-Convert cleanly."""
    try:
        require_permission(MENU, "CanRejectPO", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        try:
            po = purchase_order_service.reject_po(db, quot, user_id=ctx.user_id)
        except purchase_order_service.PurchaseOrderConflictError as exc:
            raise HTTPException(409, str(exc))
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="PO Rejected (un-Converted)", status=quot.status,
            user_id=ctx.user_id,
            details=f"PO {po.poNo} → Rejected; quotation back to Approved",
        )
        db.commit()
        db.refresh(quot)
        return quot
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="PO Reject", user_id=ctx.user_id, exc=e)
        raise


# ---------------------------------------------------------------------------
# Phase 1.5 — Final Working Sheet (Stage-2 BOM) CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/{quot_id}/purchase-order/working-sheet",
    response_model=List[QuotPOWorkingSheetLineResponse],
)
def list_po_working_sheet(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """List active Final Working Sheet lines for the captured PO.
    Returns an empty list when no PO has been captured yet."""
    require_permission(MENU, "CanRead", ctx)
    quot = _get_quot_or_403(db, quot_id, ctx)
    po = purchase_order_service.get_po(db, quot)
    if po is None:
        return []
    return po_working_sheet_service.list_lines(db, po)


@router.post(
    "/{quot_id}/purchase-order/working-sheet",
    response_model=QuotPOWorkingSheetLineResponse,
    status_code=201,
)
def add_po_working_sheet_line(
    quot_id: int,
    body: QuotPOWorkingSheetLineBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Add a new Final Working Sheet line. Allowed only while the
    PO is in Draft. Reuses ``CanEdit`` on the Quotations menu — the
    line CRUD is sub-resource of the PO and the route layer already
    holds the F2/F5/F6 visibility filter via ``_get_quot_or_403``."""
    try:
        require_permission(MENU, "CanEdit", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        po = purchase_order_service.get_po(db, quot)
        if po is None:
            raise HTTPException(404, "No purchase order on this quotation.")
        try:
            line = po_working_sheet_service.add_line(
                db, po, body, user_id=ctx.user_id,
            )
        except po_working_sheet_service.WorkingSheetLockedError as exc:
            raise HTTPException(409, str(exc))
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="PO Working Sheet line added", status=quot.status,
            user_id=ctx.user_id,
            details=f"line {line.poWorkingSheetId}",
        )
        db.commit()
        db.refresh(line)
        return line
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="PO Working Sheet add", user_id=ctx.user_id, exc=e)
        raise


@router.put(
    "/{quot_id}/purchase-order/working-sheet/{line_id}",
    response_model=QuotPOWorkingSheetLineResponse,
)
def update_po_working_sheet_line(
    quot_id: int,
    line_id: int,
    body: QuotPOWorkingSheetLineBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Edit one Final Working Sheet line. Allowed only while the PO
    is in Draft."""
    try:
        require_permission(MENU, "CanEdit", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        po = purchase_order_service.get_po(db, quot)
        if po is None:
            raise HTTPException(404, "No purchase order on this quotation.")
        try:
            line = po_working_sheet_service.update_line(
                db, po, line_id, body, user_id=ctx.user_id,
            )
        except po_working_sheet_service.WorkingSheetLockedError as exc:
            raise HTTPException(409, str(exc))
        except po_working_sheet_service.WorkingSheetNotFoundError as exc:
            raise HTTPException(404, str(exc))
        db.commit()
        db.refresh(line)
        return line
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="PO Working Sheet update", user_id=ctx.user_id, exc=e)
        raise


@router.delete(
    "/{quot_id}/purchase-order/working-sheet/{line_id}",
    status_code=204,
)
def delete_po_working_sheet_line(
    quot_id: int,
    line_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Soft-delete one Final Working Sheet line. Allowed only while
    the PO is in Draft."""
    try:
        require_permission(MENU, "CanEdit", ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)
        po = purchase_order_service.get_po(db, quot)
        if po is None:
            raise HTTPException(404, "No purchase order on this quotation.")
        try:
            po_working_sheet_service.delete_line(
                db, po, line_id, user_id=ctx.user_id,
            )
        except po_working_sheet_service.WorkingSheetLockedError as exc:
            raise HTTPException(409, str(exc))
        except po_working_sheet_service.WorkingSheetNotFoundError as exc:
            raise HTTPException(404, str(exc))
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action="PO Working Sheet line deleted", status=quot.status,
            user_id=ctx.user_id,
            details=f"line {line_id}",
        )
        db.commit()
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action="PO Working Sheet delete", user_id=ctx.user_id, exc=e)
        raise


@router.post("/{quot_id}/{stage}/unlock-edit", status_code=201)
def unlock_edit_stage(
    quot_id: int,
    stage: str,
    body: UnlockEditBody,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Privileged escape valve. Per-stage permission flag gates the
    action; the underlying entity row is NOT mutated — this just
    writes a ``LifecycleUnlockAudit`` row so admins can trace the
    override. The frontend then unhides edit affordances on that row
    for the current user's session.

    URL stage segment accepts ``quotation``, ``purchase-order``,
    ``viability``, ``annexure``.
    """
    try:
        canonical_stage = lifecycle_service.resolve_stage(stage)
        if canonical_stage is None:
            raise HTTPException(404, f"Unknown lifecycle stage: {stage!r}")

        flag = lifecycle_service.STAGE_TO_UNLOCK_FLAG[canonical_stage]
        require_permission(MENU, flag, ctx)

        quot = _get_quot_or_403(db, quot_id, ctx)

        # Resolve the entity ID for the audit row. For the quotation
        # itself it's the quotId; for downstream stages we look up the
        # current head via the same model the API surface uses.
        if canonical_stage == lifecycle_service.STAGE_QUOTATION:
            entity_id = quot.quotId
        elif canonical_stage == lifecycle_service.STAGE_PURCHASE_ORDER:
            po = purchase_order_service.get_po(db, quot)
            if po is None:
                raise HTTPException(404, "No purchase order to unlock.")
            entity_id = po.quotPOId
        elif canonical_stage == lifecycle_service.STAGE_VIABILITY:
            sheet = (
                db.query(QuotViabilitySheet)
                .filter(
                    QuotViabilitySheet.quotId == quot.quotId,
                    QuotViabilitySheet.isActive == True,  # noqa: E712
                )
                .first()
            )
            if sheet is None:
                raise HTTPException(404, "No viability sheet to unlock.")
            entity_id = sheet.viabilityId
        else:  # ANNEXURE
            ann = (
                db.query(QuotAnnexure)
                .filter(
                    QuotAnnexure.quotId == quot.quotId,
                    QuotAnnexure.isActive == True,  # noqa: E712
                )
                .first()
            )
            if ann is None:
                raise HTTPException(404, "No annexure to unlock.")
            entity_id = ann.annexureId

        audit = lifecycle_service.write_unlock_audit(
            db,
            company_id=quot.companyId,
            stage=canonical_stage,
            entity_id=entity_id,
            user_id=ctx.user_id,
            reason=body.reason,
        )
        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action=f"Unlocked {canonical_stage}", status=quot.status,
            user_id=ctx.user_id,
            details=(body.reason or None),
        )
        db.commit()
        return {
            "auditId": audit.auditId,
            "stage": canonical_stage,
            "entityId": entity_id,
            "unlockedOn": audit.unlockedOn,
            "reason": audit.reason,
        }
    except Exception as e:
        log_failure(db, quot_id=quot_id, company_id=ctx.company_id,
                    action=f"Unlock {stage}", user_id=ctx.user_id, exc=e)
        raise


# ---------------------------------------------------------------------------
# Phase 2 — Time-travel: list versions + restore past version per stage
# ---------------------------------------------------------------------------

def _po_summary(row) -> str:
    return f"PO {row.poNo} dated {row.poDate}"


def _viability_summary(row) -> str:
    return f"Viability {row.status}"


def _annexure_summary(row) -> str:
    return f"Annexure {row.status}"


def _to_version_item(
    row, *, entity_id_field: str, summary_fn,
    parent_field: str,
) -> dict:
    """Map a stage row to the uniform StageVersionListItem shape."""
    return {
        "entityId": getattr(row, entity_id_field),
        "versionNo": row.versionNo or 1,
        "isHead": bool(row.isActive),
        "status": getattr(row, "status", None),
        "parentVersionId": getattr(row, parent_field, None),
        "createdon": row.createdon,
        "createdby": row.createdby,
        "summary": summary_fn(row),
    }


@router.get(
    "/{quot_id}/{stage}/versions",
    response_model=List[StageVersionListItem],
)
def list_stage_versions(
    quot_id: int,
    stage: str,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """List every version of the given stage (head + archived) for
    this quotation. Powers the time-travel dropdown on each stage
    card. Stage segment matches the canonical Phase-1 vocabulary:
    ``purchase-order`` / ``viability`` / ``annexure``."""
    require_permission(MENU, "CanRead", ctx)
    canonical_stage = lifecycle_service.resolve_stage(stage)
    if canonical_stage is None:
        raise HTTPException(404, f"Unknown lifecycle stage: {stage!r}")
    quot = _get_quot_or_403(db, quot_id, ctx)

    if canonical_stage == lifecycle_service.STAGE_PURCHASE_ORDER:
        rows = purchase_order_service.list_po_versions(db, quot)
        return [
            _to_version_item(
                r, entity_id_field="quotPOId",
                parent_field="parentPOId", summary_fn=_po_summary,
            )
            for r in rows
        ]
    if canonical_stage == lifecycle_service.STAGE_VIABILITY:
        rows = viability_service.list_viability_versions(db, quot)
        return [
            _to_version_item(
                r, entity_id_field="viabilityId",
                parent_field="parentViabilityId", summary_fn=_viability_summary,
            )
            for r in rows
        ]
    if canonical_stage == lifecycle_service.STAGE_ANNEXURE:
        rows = annexure_service.list_annexure_versions(db, quot)
        return [
            _to_version_item(
                r, entity_id_field="annexureId",
                parent_field="parentAnnexureId", summary_fn=_annexure_summary,
            )
            for r in rows
        ]
    # The Quotation stage already has its own /versions endpoint.
    raise HTTPException(
        400,
        "Use GET /quotations/{id}/versions for the Quotation stage.",
    )


@router.post(
    "/{quot_id}/{stage}/versions/{version_id}/restore",
    status_code=201,
)
def restore_stage_version(
    quot_id: int,
    stage: str,
    version_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Clone an archived version of the given stage forward as a new
    head. Privileged: requires the matching ``CanUnlockEdit{Stage}``
    permission so the same role gate as the in-place Unlock-and-Edit
    escape applies. Side-effects:

    * Current head row → ``isActive = False``.
    * New row inserted with ``versionNo = MAX + 1``,
      ``parentXxxId = chain root``, ``status = 'Draft'``, body
      cloned from the target version.
    * Sub-rows (PO working sheet / viability lines) are cloned
      under the new entity id where applicable.
    """
    canonical_stage = lifecycle_service.resolve_stage(stage)
    if canonical_stage is None:
        raise HTTPException(404, f"Unknown lifecycle stage: {stage!r}")
    flag = lifecycle_service.STAGE_TO_UNLOCK_FLAG.get(canonical_stage)
    if flag is None:
        raise HTTPException(
            400,
            "Restore is only available for PurchaseOrder, Viability, and Annexure stages.",
        )

    try:
        require_permission(MENU, flag, ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)

        if canonical_stage == lifecycle_service.STAGE_PURCHASE_ORDER:
            try:
                new_row = purchase_order_service.restore_po_version(
                    db, quot, version_id, user_id=ctx.user_id,
                )
            except purchase_order_service.PurchaseOrderConflictError as exc:
                raise HTTPException(404, str(exc))
            new_id = new_row.quotPOId
        elif canonical_stage == lifecycle_service.STAGE_VIABILITY:
            try:
                new_row = viability_service.restore_viability_version(
                    db, quot, version_id, user_id=ctx.user_id,
                )
            except ValueError as exc:
                raise HTTPException(404, str(exc))
            new_id = new_row.viabilityId
        elif canonical_stage == lifecycle_service.STAGE_ANNEXURE:
            try:
                new_row = annexure_service.restore_annexure_version(
                    db, quot, version_id, user_id=ctx.user_id,
                )
            except ValueError as exc:
                raise HTTPException(404, str(exc))
            new_id = new_row.annexureId
        else:
            raise HTTPException(400, "Unsupported stage for restore.")

        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action=f"Restored {canonical_stage} v{getattr(new_row, 'versionNo', '?')}",
            status=quot.status,
            user_id=ctx.user_id,
            details=f"Source version id={version_id}; new entity id={new_id}",
        )
        db.commit()
        db.refresh(new_row)
        return {
            "stage": canonical_stage,
            "newEntityId": new_id,
            "newVersionNo": new_row.versionNo,
        }
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action=f"Restore {stage}", user_id=ctx.user_id, exc=e,
        )
        raise


# ---------------------------------------------------------------------------
# Phase 3 — Re-source from latest upstream
# ---------------------------------------------------------------------------

@router.post(
    "/{quot_id}/{stage}/re-source",
    status_code=201,
)
def re_source_stage(
    quot_id: int,
    stage: str,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Re-source a downstream stage from its current upstream head.

    Use case: an upstream stage moved past the version this stage
    was sourced from (e.g. quotation Revised after PO captured, PO
    re-sourced after viability generated, etc.). This archives the
    current stage head and creates a new version sourced from the
    current upstream state. Per-stage logic:

    * ``purchase-order``: re-clones the Final Working Sheet from the
      current quotation's QuotDetails. PO header copied from previous
      head; user can re-edit and re-Submit.
    * ``viability``: re-runs the viability generator against the
      current PO Working Sheet.
    * ``annexure``: re-runs annexure auto-fill from the current
      quotation + PO + viability heads.

    Privileged: requires the matching ``CanUnlockEdit{Stage}`` since
    this changes the head version (same gate as Restore).
    """
    canonical_stage = lifecycle_service.resolve_stage(stage)
    if canonical_stage is None:
        raise HTTPException(404, f"Unknown lifecycle stage: {stage!r}")
    flag = lifecycle_service.STAGE_TO_UNLOCK_FLAG.get(canonical_stage)
    if flag is None or canonical_stage == lifecycle_service.STAGE_QUOTATION:
        raise HTTPException(
            400,
            "Re-source is only available for PurchaseOrder, Viability, and Annexure stages.",
        )

    try:
        require_permission(MENU, flag, ctx)
        quot = _get_quot_or_403(db, quot_id, ctx)

        if canonical_stage == lifecycle_service.STAGE_PURCHASE_ORDER:
            try:
                new_row = purchase_order_service.re_source_po_from_quotation(
                    db, quot, user_id=ctx.user_id,
                )
            except purchase_order_service.PurchaseOrderConflictError as exc:
                raise HTTPException(409, str(exc))
            new_id = new_row.quotPOId
        elif canonical_stage == lifecycle_service.STAGE_VIABILITY:
            new_row = viability_service.re_source_viability_from_po(
                db, quot, user_id=ctx.user_id,
            )
            new_id = new_row.viabilityId
        else:  # ANNEXURE
            try:
                new_row = annexure_service.re_source_annexure_from_upstream(
                    db, quotation=quot, user_id=ctx.user_id,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            new_id = new_row.annexureId

        log_action(
            db, quot_id=quot.quotId, company_id=quot.companyId,
            action=f"Re-sourced {canonical_stage} v{getattr(new_row, 'versionNo', '?')}",
            status=quot.status,
            user_id=ctx.user_id,
            details=f"new entity id={new_id}",
        )
        db.commit()
        db.refresh(new_row)
        return {
            "stage": canonical_stage,
            "newEntityId": new_id,
            "newVersionNo": getattr(new_row, "versionNo", None),
        }
    except Exception as e:
        log_failure(
            db, quot_id=quot_id, company_id=ctx.company_id,
            action=f"Re-source {stage}", user_id=ctx.user_id, exc=e,
        )
        raise


# --- TP Cost Lookup ---

@router.get("/tp-cost/{dia}")
def get_tp_cost(
    dia: str,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Get latest TP cost from RawMaterialCost for a given dia."""
    tp_cost = get_tp_cost_for_dia(db, ctx.company_id, dia)
    return {"dia": dia, "tpcost": tp_cost}


# ===== Quotation Details =====

@router.get("/{quot_id}/purchase-order/working-sheet/export-excel")
def export_po_working_sheet_excel(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Download the PO's Final Working Sheet as XLSX. Uses the same
    formatter as the quotation export (``build_quotation_xlsx``) since
    the column shape matches QuotDetails — only the header context
    swaps to the PO's own customer / site / PO No / PO Date."""
    from fastapi.responses import Response
    from app.services.quotation_excel_service import build_quotation_xlsx
    from app.models.customer import CustomerMaster, CustomerSite
    from app.models.quot_po_working_sheet import QuotPOWorkingSheet

    require_permission(MENU, "CanRead", ctx)
    quot = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(quot, ctx)

    po = purchase_order_service.get_po(db, quot)
    if po is None:
        raise HTTPException(404, "No purchase order on this quotation.")

    # Fetch active working-sheet rows.
    items = (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.quotPOId == po.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .order_by(QuotPOWorkingSheet.poWorkingSheetId.asc())
        .all()
    )
    detail_dicts = [
        {c.key: getattr(d, c.key, None) for c in d.__table__.columns}
        for d in items
    ]

    # Header context — pulled from the PO entity, not the quotation,
    # so the export reflects what was actually ordered (which can
    # differ from the quoted side under group-company billing etc.).
    customer = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == po.customerId,
        CustomerMaster.companyId == ctx.company_id,
    ).first()
    site = None
    if po.billingSiteId:
        site = db.query(CustomerSite).filter(
            CustomerSite.siteId == po.billingSiteId,
        ).first()

    xlsx_bytes = build_quotation_xlsx(
        client_name=customer.customerName if customer else "",
        site_name=(site.siteAddressCode if site else "") or "",
        payment_terms="",
        tp_ref_dia="16",
        quot_date=po.poDate.strftime("%d-%b-%Y") if po.poDate else "",
        quot_no=po.poNo or "",
        details=detail_dicts,
    )

    safe_no = (po.poNo or f"po-{po.quotPOId}").replace("/", "-").replace("\\", "-")
    filename = f"{safe_no}-final-working-sheet.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{quot_id}/details/export-excel")
def export_quotation_details_excel(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Download line items as XLSX in the standard quotation working format."""
    from fastapi.responses import Response
    from app.services.quotation_excel_service import build_quotation_xlsx
    from app.models.customer import CustomerMaster, CustomerSite
    from datetime import datetime as _dt

    require_permission(MENU, "CanRead", ctx)
    quot = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(quot, ctx)

    # Fetch line items
    items = db.query(QuotDetails).filter(
        QuotDetails.quotId == quot_id,
        QuotDetails.isActive == True,
    ).all()

    # Convert ORM rows to dicts
    detail_dicts = []
    for d in items:
        row = {c.key: getattr(d, c.key, None) for c in d.__table__.columns}
        # Append unit to length for display ("12 MTRS" already contains unit)
        detail_dicts.append(row)

    # Header context
    customer = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == quot.customerId,
        CustomerMaster.companyId == ctx.company_id,
    ).first()
    site = None
    if quot.siteId:
        site = db.query(CustomerSite).filter(CustomerSite.siteId == quot.siteId).first()

    # Determine T.P. Ref dia (use 16 by default; could be derived from quot subject)
    tp_ref_dia = "16"

    xlsx_bytes = build_quotation_xlsx(
        client_name=customer.customerName if customer else "",
        site_name=(site.siteAddressCode if site else "") or "",
        payment_terms="",
        tp_ref_dia=tp_ref_dia,
        quot_date=quot.quotDate.strftime("%d-%b-%Y") if quot.quotDate else "",
        quot_no=quot.quotNo or "",
        details=detail_dicts,
    )

    safe_no = (quot.quotNo or f"quot-{quot_id}").replace("/", "-").replace("\\", "-")
    filename = f"{safe_no}-line-items.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.get("/{quot_id}/details", response_model=List[QuotDetailResponse])
def get_quotation_details(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    return db.query(QuotDetails).filter(
        QuotDetails.quotId == quot_id,
        QuotDetails.isActive == True,
    ).all()


def _is_for_delivery_term(quotation: QuotSummary) -> bool:
    """True when the quotation's delivery term reads as 'FOR' (token match,
    case-insensitive). FOR = Free On Rail / Free On Road — seller bears
    freight to destination, so the freight column matching the chosen
    delivery mode must carry a value. The other mode's column is locked.
    """
    term = quotation.delivery_term.deliveryTerm if quotation.delivery_term else None
    if not term:
        return False
    return "for" in term.strip().lower().split()


def _delivery_mode_name(quotation: QuotSummary) -> str:
    """Selected delivery mode's display name, lowercased. Empty when no
    mode is set yet — caller treats that as 'don't lock either column'."""
    mode = quotation.delivery_mode.deliveryMode if quotation.delivery_mode else None
    return (mode or "").strip().lower()


# Tolerant matchers — cope with whatever spelling the master holds
# ("Trailer", "Trailor", "By Trailer Straight Length", "Truck", "Trk",
# "Lorry"). Mirrored on the frontend lock helpers so server and client
# agree on which side is editable.
_TRAILER_RE = re.compile(r"trail|trial", re.IGNORECASE)
_TRUCK_RE = re.compile(r"truck|trk|lorr", re.IGNORECASE)


def _mode_is_trailer(mode: str) -> bool:
    return bool(_TRAILER_RE.search(mode or ""))


def _mode_is_truck(mode: str) -> bool:
    return bool(_TRUCK_RE.search(mode or ""))


def _apply_freight_rule(
    payload: dict, quotation: QuotSummary
) -> dict:
    """Mutate the detail payload in place per the term + mode rules:

    - Non-FOR (Ex-Factory etc.) → zero BOTH freight columns. Buyer arranges
      transport, so seller-side freight is irrelevant.
    - FOR + Trailer → zero FreightTruck (Trailer column is the live one).
    - FOR + Truck   → zero FreightTrailer.
    - FOR + no mode (or unrecognised mode) → zero BOTH.

    FOR-mandatory enforcement (the matching column must be > 0) happens at
    /approve time so partial drafts aren't blocked from saving.
    """
    if not _is_for_delivery_term(quotation):
        payload["FreightTrailer"] = 0
        payload["FreightTruck"] = 0
        return payload
    mode = _delivery_mode_name(quotation)
    if not mode:
        payload["FreightTrailer"] = 0
        payload["FreightTruck"] = 0
        return payload
    if _mode_is_trailer(mode):
        payload["FreightTruck"] = 0
    elif _mode_is_truck(mode):
        payload["FreightTrailer"] = 0
    else:
        payload["FreightTrailer"] = 0
        payload["FreightTruck"] = 0
    return payload


@router.post("/{quot_id}/details", response_model=QuotDetailResponse, status_code=201)
def create_quotation_detail(
    quot_id: int,
    data: QuotDetailCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    detail_payload = _apply_freight_rule(data.model_dump(), parent)
    detail = QuotDetails(
        **detail_payload,
        quotId=quot_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(detail)
    db.flush()
    log_action(db, quot_id=quot_id, company_id=ctx.company_id,
               action="Line item added", status=parent.status, user_id=ctx.user_id,
               details=f"{detail.itemGradeName or ''} Dia {detail.itemDia or '-'} "
                       f"Qty {detail.quantity or 0}".strip())
    db.commit()
    db.refresh(detail)
    return detail


@router.put("/{quot_id}/details/{dtl_id}", response_model=QuotDetailResponse)
def update_quotation_detail(
    quot_id: int,
    dtl_id: int,
    data: QuotDetailCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    detail = db.query(QuotDetails).filter(
        QuotDetails.quotDtlId == dtl_id,
        QuotDetails.quotId == quot_id,
        QuotDetails.isActive == True,
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Detail not found")
    payload = _apply_freight_rule(data.model_dump(exclude_unset=True), parent)
    changed_fields = []
    for k, v in payload.items():
        if getattr(detail, k, None) != v:
            changed_fields.append(k)
        setattr(detail, k, v)
    detail.lastupdateby = ctx.user_id
    if changed_fields:
        log_action(db, quot_id=quot_id, company_id=ctx.company_id,
                   action="Line item updated", status=parent.status, user_id=ctx.user_id,
                   details=f"dtlId={dtl_id} · fields: {', '.join(changed_fields)}")
    db.commit()
    db.refresh(detail)
    return detail


@router.delete("/{quot_id}/details/{dtl_id}", status_code=204)
def delete_quotation_detail(
    quot_id: int,
    dtl_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    detail = db.query(QuotDetails).filter(
        QuotDetails.quotDtlId == dtl_id,
        QuotDetails.quotId == quot_id,
        QuotDetails.isActive == True,
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Detail not found")
    detail.isActive = False
    detail.lastupdateby = ctx.user_id
    log_action(db, quot_id=quot_id, company_id=ctx.company_id,
               action="Line item deleted", status=parent.status, user_id=ctx.user_id,
               details=f"dtlId={dtl_id} · {detail.itemGradeName or ''} Dia {detail.itemDia or '-'}".strip())
    db.commit()


@router.post("/{quot_id}/details/from-enquiry/{enq_id}", response_model=List[QuotDetailResponse], status_code=201)
def import_details_from_enquiry(
    quot_id: int,
    enq_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Import line items from enquiry details + latest costing version into quotation details."""
    require_permission(MENU, "CanEdit", ctx)
    quot_parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(quot_parent, ctx)
    # Validate source enquiry visibility
    enq_parent = db.query(CustomerEnquiry).filter(
        CustomerEnquiry.enqid == enq_id,
        CustomerEnquiry.companyId == ctx.company_id,
        CustomerEnquiry.isActive == True,
    ).first()
    if not enq_parent:
        raise HTTPException(404, "Source enquiry not found")
    require_owner_visible(enq_parent.ownerUserId, ctx)

    enq_details = db.query(CustomerEnquiryDetails).filter(
        CustomerEnquiryDetails.enqid == enq_id,
        CustomerEnquiryDetails.companyId == ctx.company_id,
        CustomerEnquiryDetails.isActive == True,
    ).all()

    if not enq_details:
        raise HTTPException(status_code=404, detail="No enquiry line items found")

    # Get latest costing version for this enquiry
    max_ver = (
        db.query(func.max(CustomerEnquiryCosting.versionNo))
        .filter(
            CustomerEnquiryCosting.enqid == enq_id,
            CustomerEnquiryCosting.isActive == True,
        )
        .scalar()
    )

    # Build costing lookup by enqdtlid
    costing_map = {}
    if max_ver:
        costings = db.query(CustomerEnquiryCosting).filter(
            CustomerEnquiryCosting.enqid == enq_id,
            CustomerEnquiryCosting.versionNo == max_ver,
            CustomerEnquiryCosting.isActive == True,
        ).all()
        costing_map = {c.enqdtlid: c for c in costings}

    created = []
    for dtl in enq_details:
        costing = costing_map.get(dtl.enqdtlid)
        cost_data = {}
        if costing:
            for col in COST_HEAD_COLS:
                val = getattr(costing, col, None)
                cost_data[col] = float(val) if val is not None else None
            # Copy calculated fields from costing
            for col in ["basicRate", "GST", "EXFORPrice"]:
                val = getattr(costing, col, None)
                if val is not None:
                    cost_data[col] = float(val)

        # Auto-fill TPWGST from RawMaterialCost if not present in costing
        if not cost_data.get("TPWGST") and dtl.itemDia:
            tp = get_tp_cost_for_dia(db, ctx.company_id, dtl.itemDia)
            if tp is not None:
                cost_data["TPWGST"] = tp

        # Calculate totRate = sum of all cost heads
        tot_rate = sum(v for v in [cost_data.get(c) for c in COST_HEAD_COLS] if v)
        gst_amount = round(tot_rate * 0.18, 2) if tot_rate else 0
        ex_for = round(tot_rate + gst_amount, 2) if tot_rate else 0

        # Resolve item name from ItemName FK
        resolved_item_name = None
        if dtl.itemid:
            from app.models.item import ItemName
            item_obj = db.query(ItemName).filter(ItemName.itemId == dtl.itemid).first()
            if item_obj:
                resolved_item_name = item_obj.itemName

        new_dtl = QuotDetails(
            companyId=ctx.company_id,
            quotId=quot_id,
            itemid=dtl.itemid,
            itemName=resolved_item_name,
            itemGradeName=dtl.itemGradeName,
            itemDia=dtl.itemDia,
            itemLength=dtl.itemLength,
            itemUnit=dtl.itemUnit,
            quantity=dtl.quantity,
            totRate=tot_rate or None,
            gstMode="IGST",
            IGST=gst_amount or None,
            CGST=None,
            SGST=None,
            totAmount=ex_for or None,
            createdby=ctx.user_id,
            **{k: v for k, v in cost_data.items() if k in COST_HEAD_COLS},
        )
        db.add(new_dtl)
        created.append(new_dtl)

    if created:
        parent = db.query(QuotSummary).filter(QuotSummary.quotId == quot_id).first()
        log_action(db, quot_id=quot_id, company_id=ctx.company_id,
                   action="Line items bulk-imported from enquiry",
                   status=parent.status if parent else None,
                   user_id=ctx.user_id,
                   details=f"enqId={enq_id} · {len(created)} line(s)")
    db.commit()
    for c in created:
        db.refresh(c)
    return created


# ===== Quotation Terms & Conditions =====

@router.get("/{quot_id}/terms", response_model=List[QuotTncResponse])
def get_quotation_terms(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    return db.query(QuotTermsNConditions).filter(
        QuotTermsNConditions.quotId == quot_id,
        QuotTermsNConditions.isActive == True,
    ).order_by(QuotTermsNConditions.sortOrder).all()


@router.post("/{quot_id}/terms/from-master", status_code=201)
def copy_terms_from_master(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Add master TnCs not already on this quotation (deduped by masterTncId only)."""
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    existing_master_ids = {
        r[0] for r in db.query(QuotTermsNConditions.masterTncId).filter(
            QuotTermsNConditions.quotId == quot_id,
            QuotTermsNConditions.isActive == True,
            QuotTermsNConditions.masterTncId != None,
        ).all()
    }

    max_order = db.query(func.max(QuotTermsNConditions.sortOrder)).filter(
        QuotTermsNConditions.quotId == quot_id,
        QuotTermsNConditions.isActive == True,
    ).scalar() or 0

    masters = db.query(TermsNConditionMaster).filter(
        TermsNConditionMaster.companyId == ctx.company_id,
        TermsNConditionMaster.isActive == True,
    ).order_by(TermsNConditionMaster.tncId).all()

    added = 0
    for m in masters:
        if m.tncId in existing_master_ids:
            continue
        max_order += 1
        db.add(QuotTermsNConditions(
            quotId=quot_id,
            companyId=ctx.company_id,
            masterTncId=m.tncId,
            tncName=m.tncName,
            tncDescription=m.tncDescription,
            sortOrder=max_order,
            createdby=ctx.user_id,
        ))
        added += 1

    if added:
        log_action(db, quot_id=quot_id, company_id=ctx.company_id,
                   action="T&C bulk-imported from master", status=parent.status,
                   user_id=ctx.user_id,
                   details=f"{added} term(s) added")
    db.commit()
    return {"message": f"Added {added} new terms from master", "added": added}


@router.post("/{quot_id}/terms/from-quotation/{source_quot_id}", status_code=201)
def copy_terms_from_quotation(
    quot_id: int,
    source_quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Import TnCs from another quotation. Deduped by masterTncId only."""
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    # Validate source quotation visibility too
    source_parent = _get_quot_or_403(db, source_quot_id, ctx)
    require_parent_visible(source_parent, ctx)

    existing = db.query(QuotTermsNConditions).filter(
        QuotTermsNConditions.quotId == quot_id,
        QuotTermsNConditions.isActive == True,
    ).all()
    existing_master_ids = {t.masterTncId for t in existing if t.masterTncId}

    max_order = max((t.sortOrder or 0 for t in existing), default=0)

    source_terms = db.query(QuotTermsNConditions).filter(
        QuotTermsNConditions.quotId == source_quot_id,
        QuotTermsNConditions.isActive == True,
    ).order_by(QuotTermsNConditions.sortOrder).all()

    added = 0
    updated = 0
    for st in source_terms:
        if st.masterTncId and st.masterTncId in existing_master_ids:
            match = next((t for t in existing if t.masterTncId == st.masterTncId), None)
            if match:
                match.tncDescription = st.tncDescription
                match.lastupdateby = ctx.user_id
                updated += 1
            continue

        max_order += 1
        new_tnc = QuotTermsNConditions(
            quotId=quot_id,
            companyId=ctx.company_id,
            masterTncId=st.masterTncId,
            tncName=st.tncName,
            tncDescription=st.tncDescription,
            sortOrder=max_order,
            createdby=ctx.user_id,
        )
        db.add(new_tnc)
        if st.masterTncId:
            existing_master_ids.add(st.masterTncId)
        added += 1

    if added or updated:
        log_action(db, quot_id=quot_id, company_id=ctx.company_id,
                   action="T&C copied from another quotation", status=parent.status,
                   user_id=ctx.user_id,
                   details=f"source quotId={source_quot_id} · {added} new, {updated} updated")
    db.commit()
    return {"message": f"Imported {added} new, updated {updated} existing", "added": added, "updated": updated}


@router.post("/{quot_id}/terms", response_model=QuotTncResponse, status_code=201)
def add_quotation_term(
    quot_id: int,
    data: QuotTncCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    tnc = QuotTermsNConditions(
        **data.model_dump(),
        quotId=quot_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(tnc)
    db.flush()
    log_action(db, quot_id=quot_id, company_id=ctx.company_id,
               action="T&C added", status=parent.status, user_id=ctx.user_id,
               details=tnc.tncName or (tnc.tncDescription[:100] if tnc.tncDescription else None))
    db.commit()
    db.refresh(tnc)
    return tnc


@router.put("/{quot_id}/terms/reorder")
def reorder_quotation_terms(
    quot_id: int,
    items: List[QuotTncReorderItem],
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    reordered = 0
    for item in items:
        tnc = db.query(QuotTermsNConditions).filter(
            QuotTermsNConditions.quotTncId == item.quotTncId,
            QuotTermsNConditions.quotId == quot_id,
            QuotTermsNConditions.isActive == True,
        ).first()
        if tnc:
            tnc.sortOrder = item.sortOrder
            tnc.lastupdateby = ctx.user_id
            reordered += 1
    if reordered:
        log_action(db, quot_id=quot_id, company_id=ctx.company_id,
                   action="T&C reordered", status=parent.status, user_id=ctx.user_id,
                   details=f"{reordered} term(s) re-sorted")
    db.commit()
    return {"message": "Order updated"}


@router.put("/{quot_id}/terms/{tnc_id}", response_model=QuotTncResponse)
def update_quotation_term(
    quot_id: int,
    tnc_id: int,
    data: QuotTncCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    tnc = db.query(QuotTermsNConditions).filter(
        QuotTermsNConditions.quotTncId == tnc_id,
        QuotTermsNConditions.quotId == quot_id,
        QuotTermsNConditions.isActive == True,
    ).first()
    if not tnc:
        raise HTTPException(status_code=404, detail="Term not found")
    payload = data.model_dump(exclude_unset=True)
    changed = []
    for k, v in payload.items():
        if getattr(tnc, k, None) != v:
            changed.append(k)
        setattr(tnc, k, v)
    tnc.lastupdateby = ctx.user_id
    if changed:
        log_action(db, quot_id=quot_id, company_id=ctx.company_id,
                   action="T&C updated", status=parent.status, user_id=ctx.user_id,
                   details=f"tncId={tnc_id} · fields: {', '.join(changed)}")
    db.commit()
    db.refresh(tnc)
    return tnc


@router.delete("/{quot_id}/terms/{tnc_id}", status_code=204)
def delete_quotation_term(
    quot_id: int,
    tnc_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    tnc = db.query(QuotTermsNConditions).filter(
        QuotTermsNConditions.quotTncId == tnc_id,
        QuotTermsNConditions.quotId == quot_id,
        QuotTermsNConditions.isActive == True,
    ).first()
    if not tnc:
        raise HTTPException(status_code=404, detail="Term not found")
    tnc.isActive = False
    tnc.lastupdateby = ctx.user_id
    log_action(db, quot_id=quot_id, company_id=ctx.company_id,
               action="T&C deleted", status=parent.status, user_id=ctx.user_id,
               details=f"tncId={tnc_id} · {tnc.tncName or ''}".strip())
    db.commit()


# ===== Quotation Follow-Ups =====

@router.get("/{quot_id}/followups", response_model=List[QuotFollowUpResponse])
def get_quot_followups(
    quot_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanRead", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    return db.query(QuotFollowUp).filter(
        QuotFollowUp.quotId == quot_id,
        QuotFollowUp.companyId == ctx.company_id,
        QuotFollowUp.isActive == True,
    ).order_by(QuotFollowUp.followupdate.desc()).all()


@router.post("/{quot_id}/followups", response_model=QuotFollowUpResponse, status_code=201)
def create_quot_followup(
    quot_id: int,
    data: QuotFollowUpCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    followup = QuotFollowUp(
        **data.model_dump(),
        quotId=quot_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    return followup


@router.put("/{quot_id}/followups/{followup_id}", response_model=QuotFollowUpResponse)
def update_quot_followup(
    quot_id: int,
    followup_id: int,
    data: QuotFollowUpCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    followup = db.query(QuotFollowUp).filter(
        QuotFollowUp.quotfollowupid == followup_id,
        QuotFollowUp.quotId == quot_id,
        QuotFollowUp.companyId == ctx.company_id,
        QuotFollowUp.isActive == True,
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


@router.delete("/{quot_id}/followups/{followup_id}")
def delete_quot_followup(
    quot_id: int,
    followup_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU, "CanEdit", ctx)
    parent = _get_quot_or_403(db, quot_id, ctx)
    require_parent_visible(parent, ctx)
    followup = db.query(QuotFollowUp).filter(
        QuotFollowUp.quotfollowupid == followup_id,
        QuotFollowUp.quotId == quot_id,
        QuotFollowUp.companyId == ctx.company_id,
        QuotFollowUp.isActive == True,
    ).first()
    if not followup:
        raise HTTPException(404, "Follow-up not found")
    followup.isActive = False
    followup.lastupdateby = ctx.user_id
    followup.lastupdateon = now_ist()
    db.commit()
    return {"message": "Follow-up deleted"}
