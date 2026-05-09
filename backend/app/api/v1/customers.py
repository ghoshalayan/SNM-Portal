from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from app.core.dependencies import get_db
from app.core.pagination import PaginationParams, paginate
from app.core.cursor_pagination import CursorParams, cursor_paginate
from app.models.customer import CustomerMaster, CustomerContacts, CustomerSite
from app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerResponse, CustomerDetailResponse,
    CustomerContactCreate, CustomerContactResponse,
    CustomerSiteCreate, CustomerSiteResponse,
)
from app.schemas.quot_purchase_order import AdHocSiteCreate
from app.services.access_service import (
    AccessContext, get_access_context,
    apply_company_filter,
    require_permission, require_location_access,
)

router = APIRouter()

MENU_CUSTOMER = "Customers"
MENU_CONTACT = "Customer Contacts"  # fall back to Customers menu perms if not defined
MENU_SITE = "Customer Sites"


# ===== Search (cursor-based, for dropdown lookups) =====

@router.get("/search")
def search_customers(
    params: CursorParams = Depends(),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Cursor-paginated search for customer dropdowns (scales to 50k+ rows).

    - Prefix-matches against customerName and customerCode (both index-friendly)
    - Returns {id, label, sub} tuples only — small payload
    - Does NOT replace the existing GET / endpoint (kept as fallback)
    """
    require_permission(MENU_CUSTOMER, "CanRead", ctx)

    q = db.query(
        CustomerMaster.customerId,
        CustomerMaster.customerName,
        CustomerMaster.customerCode,
    ).filter(CustomerMaster.isActive == True)
    q = apply_company_filter(q, CustomerMaster.companyId, ctx)

    # id-lookup mode: resolve specific ids to labels (used by edit mode)
    if params.ids:
        rows = q.filter(CustomerMaster.customerId.in_(params.ids)).all()
        return {
            "items": [
                {"id": r.customerId, "label": r.customerName, "sub": r.customerCode}
                for r in rows
            ],
            "nextCursor": None, "hasMore": False,
        }

    if params.q:
        term = f"{params.q}%"  # prefix match uses index
        q = q.filter(
            (CustomerMaster.customerName.ilike(term))
            | (CustomerMaster.customerCode.ilike(term))
        )

    rows, next_cursor, has_more = cursor_paginate(q, CustomerMaster.customerId, params)
    return {
        "items": [
            {"id": r.customerId, "label": r.customerName, "sub": r.customerCode}
            for r in rows
        ],
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


# ===== Customer Master =====
# Per business rule: Customers are COMPANY-WIDE visible if the Customers menu
# permission is granted. No hierarchy filter, no location filter at master level.

@router.get("")
def get_customers(
    classificationId: Optional[int] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU_CUSTOMER, "CanRead", ctx)
    q = db.query(CustomerMaster).options(
        joinedload(CustomerMaster.classification)
    ).filter(CustomerMaster.isActive == True)
    q = apply_company_filter(q, CustomerMaster.companyId, ctx)

    if pagination.search:
        q = q.filter(
            (CustomerMaster.customerName.ilike(f"%{pagination.search}%")) |
            (CustomerMaster.customerCode.ilike(f"%{pagination.search}%")) |
            (CustomerMaster.GSTN.ilike(f"%{pagination.search}%"))
        )
    if classificationId:
        q = q.filter(CustomerMaster.classificationId == classificationId)

    from app.core.pagination import resolve_sort_column
    _ALLOWED_CUSTOMER_SORT = {
        "customerId",       # default descending sort used by the list UI
        "customerCode", "customerName", "GSTN", "PAN",
        "createdon", "lastupdateon",
    }
    sort_col = resolve_sort_column(
        CustomerMaster, pagination.sort_by, allowed=_ALLOWED_CUSTOMER_SORT,
    )
    if sort_col is not None:
        q = q.order_by(sort_col.desc() if pagination.sort_dir == "desc" else sort_col.asc())
    else:
        q = q.order_by(CustomerMaster.customerName.asc())

    result = paginate(q, pagination)
    items = []
    for customer in result["items"]:
        d = {c.key: getattr(customer, c.key) for c in CustomerMaster.__table__.columns}
        d["classificationName"] = (
            customer.classification.classificationName if customer.classification else None
        )
        items.append(d)
    result["items"] = items
    return result


@router.get("/{customer_id}", response_model=CustomerDetailResponse)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU_CUSTOMER, "CanRead", ctx)
    customer = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == customer_id,
        CustomerMaster.companyId == ctx.company_id,
        CustomerMaster.isActive == True,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Sub-resource location filter applies to contacts/sites (users see subset)
    contacts_q = db.query(CustomerContacts).filter(
        CustomerContacts.customerId == customer_id,
        CustomerContacts.isActive == True,
    )
    loc_filt_c = ctx.location.build_sql_filter(CustomerContacts.state, CustomerContacts.dist)
    if loc_filt_c is False:
        contacts = []
    else:
        if loc_filt_c is not None:
            contacts_q = contacts_q.filter(loc_filt_c)
        contacts = contacts_q.all()

    sites_q = db.query(CustomerSite).filter(
        CustomerSite.customerId == customer_id,
        CustomerSite.isActive == True,
    )
    loc_filt_s = ctx.location.build_sql_filter(CustomerSite.state, CustomerSite.dist)
    if loc_filt_s is False:
        sites = []
    else:
        if loc_filt_s is not None:
            sites_q = sites_q.filter(loc_filt_s)
        sites = sites_q.all()

    return CustomerDetailResponse(
        **{c.key: getattr(customer, c.key) for c in CustomerMaster.__table__.columns},
        contacts=contacts,
        sites=sites,
    )


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU_CUSTOMER, "CanAdd", ctx)

    payload = data.model_dump()

    # Auto-generate a placeholder code when the user leaves it blank.
    # Format: TEMP00001, TEMP00002, … per company. The user can rename later
    # to a real ERP code. We fetch existing TEMP-prefixed codes in Python
    # rather than relying on DB-specific SUBSTRING/CAST so the same logic
    # works against both SQL Server and SQLite (used by tests).
    code = (payload.get("customerCode") or "").strip()
    if not code:
        existing = (
            db.query(CustomerMaster.customerCode)
            .filter(
                CustomerMaster.companyId == ctx.company_id,
                CustomerMaster.customerCode.like("TEMP%"),
            )
            .all()
        )
        max_n = 0
        for (cc,) in existing:
            if cc and len(cc) > 4:
                tail = cc[4:]
                if tail.isdigit():
                    max_n = max(max_n, int(tail))
        payload["customerCode"] = f"TEMP{max_n + 1:05d}"

    customer = CustomerMaster(
        **payload,
        companyId=ctx.company_id,
        ownerUserId=ctx.user_id,
        ownerRoleId=ctx.role_id,
        createdby=ctx.user_id,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU_CUSTOMER, "CanEdit", ctx)
    customer = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == customer_id,
        CustomerMaster.companyId == ctx.company_id,
        CustomerMaster.isActive == True,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(customer, k, v)
    customer.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    require_permission(MENU_CUSTOMER, "CanDelete", ctx)
    customer = db.query(CustomerMaster).filter(
        CustomerMaster.customerId == customer_id,
        CustomerMaster.companyId == ctx.company_id,
        CustomerMaster.isActive == True,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.isActive = False
    customer.lastupdateby = ctx.user_id
    db.commit()


# ===== Customer Contacts =====
# Location-filtered (F6). Menu permission falls back to Customers if no dedicated menu.

def _perm(ctx: AccessContext, primary_menu: str, fallback_menu: str, action: str):
    """Check primary menu permission, fallback to another menu if not defined."""
    if ctx.is_super_admin:
        return
    primary = ctx._get_menu_perm(primary_menu)
    if primary is not None:
        if not bool(getattr(primary, action, False)):
            raise HTTPException(403, f"Permission denied: {action} on {primary_menu}")
        return
    # Fallback
    require_permission(fallback_menu, action, ctx)


@router.get("/{customer_id}/contacts", response_model=List[CustomerContactResponse])
def get_contacts(
    customer_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_CONTACT, MENU_CUSTOMER, "CanRead")
    q = db.query(CustomerContacts).options(
        joinedload(CustomerContacts.contact_type)
    ).filter(
        CustomerContacts.customerId == customer_id,
        CustomerContacts.companyId == ctx.company_id,
        CustomerContacts.isActive == True,
    )
    loc_filter = ctx.location.build_sql_filter(CustomerContacts.state, CustomerContacts.dist)
    if loc_filter is False:
        return []
    if loc_filter is not None:
        q = q.filter(loc_filter)

    results = []
    for c in q.all():
        data = CustomerContactResponse.model_validate(c).model_dump()
        data["contactTypeName"] = c.contact_type.contactType if c.contact_type else None
        results.append(data)
    return results


@router.post("/{customer_id}/contacts", response_model=CustomerContactResponse, status_code=201)
def create_contact(
    customer_id: int,
    data: CustomerContactCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_CONTACT, MENU_CUSTOMER, "CanAdd")
    require_location_access(data.state, data.dist, ctx)
    contact = CustomerContacts(
        **data.model_dump(),
        customerId=customer_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.put("/{customer_id}/contacts/{contact_id}", response_model=CustomerContactResponse)
def update_contact(
    customer_id: int,
    contact_id: int,
    data: CustomerContactCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_CONTACT, MENU_CUSTOMER, "CanEdit")
    contact = db.query(CustomerContacts).filter(
        CustomerContacts.customerContactId == contact_id,
        CustomerContacts.customerId == customer_id,
        CustomerContacts.isActive == True,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    # Existing + target location must both be accessible
    require_location_access(
        contact.state, contact.dist, ctx,
        detail="You do not have access to this contact's existing location",
    )
    if data.state:
        require_location_access(
            data.state, data.dist, ctx,
            detail="You do not have access to the target location",
        )
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(contact, k, v)
    contact.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{customer_id}/contacts/{contact_id}", status_code=204)
def delete_contact(
    customer_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_CONTACT, MENU_CUSTOMER, "CanDelete")
    contact = db.query(CustomerContacts).filter(
        CustomerContacts.customerContactId == contact_id,
        CustomerContacts.customerId == customer_id,
        CustomerContacts.isActive == True,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    require_location_access(
        contact.state, contact.dist, ctx,
        detail="You do not have access to this contact's location",
    )
    contact.isActive = False
    contact.lastupdateby = ctx.user_id
    db.commit()


# ===== Customer Sites =====

@router.get("/{customer_id}/sites", response_model=List[CustomerSiteResponse])
def get_sites(
    customer_id: int,
    includeAdHoc: bool = Query(
        False,
        description=(
            "Include sites flagged isAdHoc=True (created from the PO "
            "manual-address flow). Default False so the regular site "
            "picker stays clean."
        ),
    ),
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_SITE, MENU_CUSTOMER, "CanRead")
    q = db.query(CustomerSite).filter(
        CustomerSite.customerId == customer_id,
        CustomerSite.companyId == ctx.company_id,
        CustomerSite.isActive == True,
    )
    if not includeAdHoc:
        q = q.filter(CustomerSite.isAdHoc == False)  # noqa: E712 — SQL Server compat
    loc_filter = ctx.location.build_sql_filter(CustomerSite.state, CustomerSite.dist)
    if loc_filter is False:
        return []
    if loc_filter is not None:
        q = q.filter(loc_filter)
    return q.all()


@router.post("/{customer_id}/sites", response_model=CustomerSiteResponse, status_code=201)
def create_site(
    customer_id: int,
    data: CustomerSiteCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_SITE, MENU_CUSTOMER, "CanAdd")
    require_location_access(data.state, data.dist, ctx)
    site = CustomerSite(
        **data.model_dump(),
        customerId=customer_id,
        companyId=ctx.company_id,
        createdby=ctx.user_id,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.post(
    "/{customer_id}/sites/ad-hoc",
    response_model=CustomerSiteResponse,
    status_code=201,
)
def create_ad_hoc_site(
    customer_id: int,
    data: AdHocSiteCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    """Create a CustomerSite from the PO dialog's "save permanently"
    flow. Stamped ``isAdHoc=False`` so it surfaces in the standard
    site picker and Customer → Sites tab — same shape as a regular
    New Site, just created from a different entry point. Same RBAC
    as a regular site create."""
    _perm(ctx, MENU_SITE, MENU_CUSTOMER, "CanAdd")
    require_location_access(data.state, data.dist, ctx)
    payload = data.model_dump()
    if not payload.get("siteAddressCode"):
        cust = db.query(CustomerMaster).filter(
            CustomerMaster.customerId == customer_id,
            CustomerMaster.companyId == ctx.company_id,
            CustomerMaster.isActive == True,  # noqa: E712 — SQL Server compat
        ).first()
        customer_code = (cust.customerCode or "").strip() if cust else ""
        existing_count = db.query(CustomerSite).filter(
            CustomerSite.customerId == customer_id,
            CustomerSite.companyId == ctx.company_id,
            CustomerSite.isActive == True,  # noqa: E712
        ).count()
        if customer_code:
            payload["siteAddressCode"] = (
                customer_code if existing_count == 0
                else f"{customer_code}/{existing_count}"
            )
    site = CustomerSite(
        **payload,
        customerId=customer_id,
        companyId=ctx.company_id,
        isAdHoc=False,
        createdby=ctx.user_id,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.put("/{customer_id}/sites/{site_id}", response_model=CustomerSiteResponse)
def update_site(
    customer_id: int,
    site_id: int,
    data: CustomerSiteCreate,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_SITE, MENU_CUSTOMER, "CanEdit")
    site = db.query(CustomerSite).filter(
        CustomerSite.siteId == site_id,
        CustomerSite.customerId == customer_id,
        CustomerSite.isActive == True,
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    require_location_access(
        site.state, site.dist, ctx,
        detail="You do not have access to this site's existing location",
    )
    if data.state:
        require_location_access(
            data.state, data.dist, ctx,
            detail="You do not have access to the target location",
        )
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(site, k, v)
    site.lastupdateby = ctx.user_id
    db.commit()
    db.refresh(site)
    return site


@router.delete("/{customer_id}/sites/{site_id}", status_code=204)
def delete_site(
    customer_id: int,
    site_id: int,
    db: Session = Depends(get_db),
    ctx: AccessContext = Depends(get_access_context),
):
    _perm(ctx, MENU_SITE, MENU_CUSTOMER, "CanDelete")
    site = db.query(CustomerSite).filter(
        CustomerSite.siteId == site_id,
        CustomerSite.customerId == customer_id,
        CustomerSite.isActive == True,
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    require_location_access(
        site.state, site.dist, ctx,
        detail="You do not have access to this site's location",
    )
    site.isActive = False
    site.lastupdateby = ctx.user_id
    db.commit()
