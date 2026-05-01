from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.security import hash_password
from app.core.pagination import PaginationParams, paginate
from app.core.cursor_pagination import CursorParams, cursor_paginate
from app.models.user import User, UserRoleMap
from app.models.user_location_map import UserLocationMap
from app.models.location import Country, StateMaster, DistrictMaster
from app.models.company import Company
from app.models.role import Role
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse, RoleMappingCreate, UserRoleMapResponse,
    LocationMappingCreate, UserLocationMapResponse, UserLocationTreeNode,
)

router = APIRouter()


def _validate_role_mappings(
    db: Session,
    mappings: List[RoleMappingCreate],
    current_user: CurrentUser,
    target_company_id: Optional[int] = None,
) -> None:
    """Validate that all companies and roles in mappings exist and are accessible.

    When `target_company_id` is supplied (user-create flow), non-SuperAdmin
    callers must keep every mapping scoped to that company — you can't stand
    up a multi-company user in a single create call unless you're a
    SuperAdmin. Multi-company setup is still reachable via the dedicated
    PUT /users/{id}/role-mappings endpoint.
    """
    for m in mappings:
        # Non-super-admins can only assign their own company
        if not current_user.is_super_admin and m.companyId != current_user.company_id:
            raise HTTPException(
                status_code=403,
                detail=f"You can only assign roles within your own company",
            )
        # When the caller gave us a target user's home company, enforce that
        # non-SuperAdmin role mappings line up with it. Stops a company-admin
        # from pinning their user to a different company via the mapping
        # side door.
        if (
            target_company_id is not None
            and not current_user.is_super_admin
            and m.companyId != target_company_id
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Role mapping companyId ({m.companyId}) must match the "
                    f"target user's companyId ({target_company_id})."
                ),
            )
        # Company must exist and be active
        company = db.query(Company).filter(
            Company.companyId == m.companyId, Company.isActive == True
        ).first()
        if not company:
            raise HTTPException(status_code=400, detail=f"Invalid or inactive company (id={m.companyId})")
        # Role must exist, be active, and belong to the specified company
        role = db.query(Role).filter(
            Role.roleId == m.roleId,
            Role.companyId == m.companyId,
            Role.isActive == True,
        ).first()
        if not role:
            raise HTTPException(status_code=400, detail=f"Invalid or inactive role (id={m.roleId}) for company (id={m.companyId})")
        # Only SuperAdmins can assign SuperAdmin roles
        if role.IsSuperAdmin and not current_user.is_super_admin:
            raise HTTPException(status_code=403, detail="Only SuperAdmins can assign SuperAdmin roles")


# ===== Search (cursor-based, for dropdown lookups) =====

@router.get("/search")
def search_users(
    params: CursorParams = Depends(),
    companyId: Optional[int] = Query(None, description="Override company filter (admin use)"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cursor-paginated user search for dropdowns (handover, reportTo, etc).

    - Prefix-matches userName, userLogin, userCode
    - Company-scoped by default (overridable via ?companyId for reportTo picker)
    - Returns {id, label, sub} only
    """
    from sqlalchemy import or_

    q = db.query(
        User.userId, User.userName, User.userCode, User.userLogin,
    ).filter(User.isActive == True)

    # Determine target company: SuperAdmin may query any; others locked to their own
    target_company = current_user.company_id
    if companyId and current_user.is_super_admin:
        target_company = companyId

    if not current_user.is_super_admin or companyId:
        # Scope to users mapped to the target company
        mapped_ids = db.query(UserRoleMap.userId).filter(
            UserRoleMap.companyId == target_company,
            UserRoleMap.isActive == True,
        ).subquery()
        q = q.filter(
            or_(
                User.companyId == target_company,
                User.userId.in_(mapped_ids),
            )
        )

    # id-lookup mode
    if params.ids:
        rows = q.filter(User.userId.in_(params.ids)).all()
        return {
            "items": [
                {"id": r.userId, "label": r.userName, "sub": r.userCode or r.userLogin}
                for r in rows
            ],
            "nextCursor": None, "hasMore": False,
        }

    if params.q:
        term = f"{params.q}%"
        q = q.filter(
            (User.userName.ilike(term))
            | (User.userLogin.ilike(term))
            | (User.userCode.ilike(term))
        )

    rows, next_cursor, has_more = cursor_paginate(q, User.userId, params)
    return {
        "items": [
            {"id": r.userId, "label": r.userName, "sub": r.userCode or r.userLogin}
            for r in rows
        ],
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }


@router.get("")
def get_users(
    companyId: Optional[int] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    target_company = companyId if companyId is not None else current_user.company_id

    # Users who have a role mapping to the target company
    mapped_user_ids = db.query(UserRoleMap.userId).filter(
        UserRoleMap.companyId == target_company,
        UserRoleMap.isActive == True,
    ).subquery()

    q = db.query(User).filter(
        User.isActive == True,
        or_(
            User.companyId == target_company,
            User.userId.in_(mapped_user_ids),
        ),
    )
    if pagination.search:
        q = q.filter(
            (User.userName.ilike(f"%{pagination.search}%")) |
            (User.userCode.ilike(f"%{pagination.search}%")) |
            (User.userEmail.ilike(f"%{pagination.search}%")) |
            (User.userLogin.ilike(f"%{pagination.search}%"))
        )

    # Sorting — whitelist so `?sortBy=userPassword` etc. can't order on
    # private columns and side-channel information via prefix probes.
    from app.core.pagination import resolve_sort_column
    _ALLOWED_USER_SORT = {
        "userId",           # permits PK as a sort default
        "userName", "userLogin", "userCode", "userEmail", "userPhone",
        "createdon", "lastupdateon",
    }
    sort_col = resolve_sort_column(
        User, pagination.sort_by, allowed=_ALLOWED_USER_SORT,
    )
    if sort_col is not None:
        q = q.order_by(sort_col.desc() if pagination.sort_dir == "desc" else sort_col.asc())
    else:
        q = q.order_by(User.userName.asc())

    result = paginate(q, pagination)

    # Resolve reportToName for each user
    report_to_ids = {u.reportTo for u in result["items"] if u.reportTo}
    if report_to_ids:
        names = {r.userId: r.userName for r in db.query(User.userId, User.userName).filter(User.userId.in_(report_to_ids)).all()}
    else:
        names = {}

    result["items"] = [
        {**UserResponse.model_validate(u).model_dump(), "reportToName": names.get(u.reportTo)}
        for u in result["items"]
    ]
    return result


# ===== Static GET routes (must be BEFORE /{user_id} to avoid path conflict) =====

@router.get("/own-code-users")
def get_own_code_users(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return users whose role has numGenMode='own_code' AND whose reportTo
    is the current user — used by select_code dropdown.

    Per RBAC v2 business rule: a Director picking a code to generate Enq/Quot
    under can only choose DIRECT REPORTS (1 level down). SuperAdmin sees all.
    """
    q = (
        db.query(User.userId, User.userName, User.userCode)
        .join(UserRoleMap, (UserRoleMap.userId == User.userId) & (UserRoleMap.isActive == True))
        .join(Role, (Role.roleId == UserRoleMap.roleId) & (Role.isActive == True))
        .filter(
            User.companyId == current_user.company_id,
            User.isActive == True,
            Role.numGenMode == "own_code",
        )
    )
    if not current_user.is_super_admin:
        # Only direct reports (reportTo = current user) in the current company
        q = q.filter(
            UserRoleMap.companyId == current_user.company_id,
            UserRoleMap.reportTo == current_user.user_id,
        )

    users = q.distinct().all()
    return [{"userId": u.userId, "userName": u.userName, "userCode": u.userCode} for u in users]


@router.get("/my-locations")
def get_my_locations(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return country→state→district tree the current user can access."""
    from app.services.location_access_service import get_location_access
    from app.models.location import Country, StateMaster, DistrictMaster

    access = get_location_access(db, current_user.user_id, current_user.company_id, current_user.is_super_admin, role_id=current_user.role_id)

    if access.is_super_admin:
        countries = db.query(Country).filter(Country.isActive == True).all()
        states = db.query(StateMaster).filter(StateMaster.isActive == True).all()
        country_list = []
        for c in countries:
            c_states = [s for s in states if s.Country == c.countryname]
            country_list.append({
                "countryid": c.countryid,
                "countryName": c.countryname,
                "states": [{"stateid": s.stateid, "StateName": s.StateName, "allDistricts": True} for s in c_states],
            })
        return {"allAccess": True, "countries": country_list}

    from app.models.user_location_map import UserLocationMap
    mappings = (
        db.query(
            UserLocationMap.countryid,
            Country.countryname,
            UserLocationMap.stateid,
            StateMaster.StateName,
            UserLocationMap.districtid,
            DistrictMaster.districName,
        )
        .join(Country, Country.countryid == UserLocationMap.countryid)
        .join(StateMaster, StateMaster.stateid == UserLocationMap.stateid)
        .outerjoin(DistrictMaster, DistrictMaster.districtid == UserLocationMap.districtid)
        .filter(
            UserLocationMap.userId == current_user.user_id,
            UserLocationMap.companyId == current_user.company_id,
            UserLocationMap.isActive == True,
        )
        .all()
    )

    if not mappings:
        return {"allAccess": False, "countries": []}

    country_map: dict = {}
    for countryid, country_name, stateid, state_name, districtid, district_name in mappings:
        if countryid not in country_map:
            country_map[countryid] = {"countryid": countryid, "countryName": country_name, "states": {}}
        state_map = country_map[countryid]["states"]
        if stateid not in state_map:
            state_map[stateid] = {"stateid": stateid, "StateName": state_name, "allDistricts": False, "districts": []}
        if districtid is None:
            state_map[stateid]["allDistricts"] = True
        elif district_name:
            state_map[stateid]["districts"].append({"districtid": districtid, "districName": district_name})

    result = []
    for c in country_map.values():
        states_list = []
        for s in c["states"].values():
            entry = {"stateid": s["stateid"], "StateName": s["StateName"], "allDistricts": s["allDistricts"]}
            if not s["allDistricts"]:
                entry["districts"] = s["districts"]
            states_list.append(entry)
        result.append({"countryid": c["countryid"], "countryName": c["countryName"], "states": states_list})

    return {"allAccess": False, "countries": result}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user = db.query(User).filter(User.userId == user_id, User.isActive == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Company-scope: non-SuperAdmins can only view users in their own company or mapped to it
    if not current_user.is_super_admin:
        is_visible = (
            user.companyId == current_user.company_id
            or db.query(UserRoleMap).filter(
                UserRoleMap.userId == user_id,
                UserRoleMap.companyId == current_user.company_id,
                UserRoleMap.isActive == True,
            ).first() is not None
        )
        if not is_visible:
            raise HTTPException(status_code=403, detail="Access denied")

    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = db.query(User).filter(User.userLogin == data.userLogin).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Non-super-admins can only create users in their own company
    if not current_user.is_super_admin:
        data.companyId = current_user.company_id

    # Validate company exists and is active
    company = db.query(Company).filter(
        Company.companyId == data.companyId, Company.isActive == True
    ).first()
    if not company:
        raise HTTPException(status_code=400, detail="Invalid or inactive company")

    # Validate role mappings (scoped to the new user's home company)
    _validate_role_mappings(
        db, data.roleMappings, current_user, target_company_id=data.companyId,
    )

    user = User(
        userName=data.userName,
        userCode=data.userCode,
        userEmail=data.userEmail,
        userPhone=data.userPhone,
        userLogin=data.userLogin,
        userPassword=hash_password(data.userPassword),
        companyId=data.companyId,
        reportTo=data.reportTo,
        createdby=current_user.user_id,
    )
    db.add(user)
    db.flush()

    for mapping in data.roleMappings:
        urm = UserRoleMap(
            userId=user.userId,
            roleId=mapping.roleId,
            companyId=mapping.companyId,
            isDefault=mapping.isDefault,
            reportTo=data.reportTo,
            createdby=current_user.user_id,
        )
        db.add(urm)

    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user = db.query(User).filter(User.userId == user_id, User.isActive == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Company-scope: non-SuperAdmins can only update users in their own company
    if not current_user.is_super_admin and user.companyId != current_user.company_id:
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)
    report_to_changed = "reportTo" in update_data

    for key, value in update_data.items():
        setattr(user, key, value)
    user.lastupdateby = current_user.user_id

    # Sync reportTo to UserRoleMap (company-scoped)
    if report_to_changed:
        urm = db.query(UserRoleMap).filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.companyId == current_user.company_id,
            UserRoleMap.isActive == True,
        ).first()
        if urm:
            urm.reportTo = update_data["reportTo"]
            urm.lastupdateby = current_user.user_id

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    user = db.query(User).filter(User.userId == user_id, User.isActive == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Company-scope: non-SuperAdmins can only delete users in their own company
    if not current_user.is_super_admin and user.companyId != current_user.company_id:
        raise HTTPException(status_code=403, detail="Access denied")

    user.isActive = False
    user.lastupdateby = current_user.user_id
    db.commit()


# --- Role Mappings sub-resource ---

@router.get("/{user_id}/role-mappings", response_model=List[UserRoleMapResponse])
def get_user_role_mappings(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    mappings = db.query(UserRoleMap).filter(
        UserRoleMap.userId == user_id,
        UserRoleMap.isActive == True,
    ).all()

    report_to_ids = {m.reportTo for m in mappings if m.reportTo}
    names = {}
    if report_to_ids:
        names = {r.userId: r.userName for r in db.query(User.userId, User.userName).filter(User.userId.in_(report_to_ids)).all()}

    return [
        {**UserRoleMapResponse.model_validate(m).model_dump(), "reportToName": names.get(m.reportTo)}
        for m in mappings
    ]


@router.post("/{user_id}/role-mappings", status_code=status.HTTP_200_OK)
def save_user_role_mappings(
    user_id: int,
    mappings: List[RoleMappingCreate],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _validate_role_mappings(db, mappings, current_user)

    # Deactivate existing
    db.query(UserRoleMap).filter(UserRoleMap.userId == user_id).update({"isActive": False})

    for m in mappings:
        existing = db.query(UserRoleMap).filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.companyId == m.companyId,
        ).first()

        if existing:
            existing.roleId = m.roleId
            existing.isDefault = m.isDefault
            existing.reportTo = m.reportTo
            existing.isActive = True
            existing.lastupdateby = current_user.user_id
        else:
            urm = UserRoleMap(
                userId=user_id,
                roleId=m.roleId,
                companyId=m.companyId,
                isDefault=m.isDefault,
                reportTo=m.reportTo,
                createdby=current_user.user_id,
            )
            db.add(urm)

    # Sync User.reportTo from the current company's mapping
    current_mapping = next((m for m in mappings if m.companyId == current_user.company_id), None)
    if current_mapping:
        user = db.query(User).filter(User.userId == user_id).first()
        if user:
            user.reportTo = current_mapping.reportTo

    db.commit()

    # RBAC v2: For each company where the target user's new role enforces
    # child-location-subset, auto-inherit the reportTo's full location set.
    # This handles both KRO creation and reassignment under a different HOD.
    from app.services.kro_location_service import inherit_from_parent
    from app.services.cache_invalidation import on_user_role_change, on_user_location_change
    inherited_count = 0
    for m in mappings:
        # Invalidate caches for this company (role+reportTo change affects visibility)
        on_user_role_change(user_id, m.companyId)
        if m.reportTo:
            inherited_count += inherit_from_parent(
                db, user_id, m.companyId, current_user.user_id,
            )
            # Location inheritance may have happened — invalidate location cache
            on_user_location_change(user_id, m.companyId)

    return {"message": "Role mappings saved", "locationsInherited": inherited_count}


# --- Location Mappings sub-resource ---

@router.get("/{user_id}/location-mappings")
def get_user_location_mappings(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return user's location mappings as a tree: countries → states → districts."""
    rows = (
        db.query(
            UserLocationMap.countryid,
            Country.countryname,
            UserLocationMap.stateid,
            StateMaster.StateName,
            UserLocationMap.districtid,
            DistrictMaster.districName,
        )
        .join(Country, UserLocationMap.countryid == Country.countryid)
        .join(StateMaster, UserLocationMap.stateid == StateMaster.stateid)
        .outerjoin(DistrictMaster, UserLocationMap.districtid == DistrictMaster.districtid)
        .filter(
            UserLocationMap.userId == user_id,
            UserLocationMap.companyId == current_user.company_id,
            UserLocationMap.isActive == True,
        )
        .order_by(Country.countryname, StateMaster.StateName, DistrictMaster.districName)
        .all()
    )

    # Build tree structure
    countries_map: dict = {}
    for cid, cname, sid, sname, did, dname in rows:
        if cid not in countries_map:
            countries_map[cid] = {"countryid": cid, "countryName": cname, "states": {}}
        states_map = countries_map[cid]["states"]
        if sid not in states_map:
            states_map[sid] = {"stateid": sid, "stateName": sname, "districts": []}
        if did is not None:
            states_map[sid]["districts"].append({"districtid": did, "districtName": dname})

    locations = []
    for country in countries_map.values():
        locations.append({
            "countryid": country["countryid"],
            "countryName": country["countryName"],
            "states": list(country["states"].values()),
        })

    return {"locations": locations}


@router.post("/{user_id}/location-mappings", status_code=status.HTTP_200_OK)
def save_user_location_mappings(
    user_id: int,
    mappings: List[LocationMappingCreate],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Replace all location mappings for a user. Expects flat list of {countryid, stateid, districtid}.

    RBAC v2 additions:
    - Validate assigning user has access to the locations being assigned (existing behavior).
    - If target user's role has enforceChildLocationSubset, validate new mappings ⊆ target's reportTo's locations.
    - After save, cascade-narrow any children of the target whose locations now fall outside the new set.
    """
    # Validate: assigning user must have the locations they're assigning (unless SuperAdmin)
    if not current_user.is_super_admin:
        from app.services.location_access_service import get_location_access
        my_access = get_location_access(db, current_user.user_id, current_user.company_id, current_user.is_super_admin, role_id=current_user.role_id)
        for m in mappings:
            state = db.query(StateMaster).filter(StateMaster.stateid == m.stateid).first()
            state_name = state.StateName if state else None
            dist_name = None
            if m.districtid:
                dist = db.query(DistrictMaster).filter(DistrictMaster.districtid == m.districtid).first()
                dist_name = dist.districName if dist else None
            if not my_access.can_access(state_name, dist_name):
                raise HTTPException(status_code=403, detail=f"You do not have access to assign location: {state_name} / {dist_name or 'All Districts'}")

    # RBAC v2: If target user's role enforces child-subset, validate against target's reportTo
    from app.services.kro_location_service import (
        validate_subset_against_parent, cascade_narrow_children,
    )
    new_tuples = [(m.countryid, m.stateid, m.districtid) for m in mappings]
    try:
        validate_subset_against_parent(db, user_id, current_user.company_id, new_tuples)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Deactivate existing for this company
    db.query(UserLocationMap).filter(
        UserLocationMap.userId == user_id,
        UserLocationMap.companyId == current_user.company_id,
    ).update({"isActive": False})

    for m in mappings:
        q = db.query(UserLocationMap).filter(
            UserLocationMap.userId == user_id,
            UserLocationMap.companyId == current_user.company_id,
            UserLocationMap.countryid == m.countryid,
            UserLocationMap.stateid == m.stateid,
        )
        if m.districtid is not None:
            q = q.filter(UserLocationMap.districtid == m.districtid)
        else:
            q = q.filter(UserLocationMap.districtid.is_(None))
        existing = q.first()

        if existing:
            existing.isActive = True
            existing.lastupdateby = current_user.user_id
        else:
            db.add(UserLocationMap(
                userId=user_id,
                companyId=current_user.company_id,
                countryid=m.countryid,
                stateid=m.stateid,
                districtid=m.districtid,
                createdby=current_user.user_id,
            ))

    db.commit()

    # Cascade-narrow any subordinates whose locations now fall outside
    cascaded = cascade_narrow_children(db, user_id, current_user.company_id, current_user.user_id)

    # Invalidate location cache for this company (cascade may have affected children)
    from app.services.cache_invalidation import on_user_location_change
    on_user_location_change(user_id, current_user.company_id)

    return {"message": "Location mappings saved", "cascadedRemovals": cascaded}
