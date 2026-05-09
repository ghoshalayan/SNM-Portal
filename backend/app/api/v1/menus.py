from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.models.menu import MenuMaster
from app.models.role import Role
from app.models.role_menu_map import RoleMenuMap
from app.schemas.menu import (
    MenuCreate, MenuUpdate, MenuResponse, MenuTreeNode,
    RoleMenuPermission, RoleMenuPermissionResponse,
)
from app.services.menu_service import build_menu_tree, get_user_menu_tree

router = APIRouter()


# --- Menu CRUD ---

@router.get("", response_model=List[MenuResponse])
def get_menus(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return db.query(MenuMaster).filter(
        MenuMaster.companyId == current_user.company_id,
        MenuMaster.isActive == True,
    ).order_by(MenuMaster.menuOrder).all()


@router.get("/tree")
def get_menu_tree(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    menus = db.query(MenuMaster).filter(
        MenuMaster.companyId == current_user.company_id,
        MenuMaster.isActive == True,
    ).all()
    return build_menu_tree(menus)


@router.get("/user-tree")
def get_user_menu_tree_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.is_super_admin:
        menus = db.query(MenuMaster).filter(
            MenuMaster.companyId == current_user.company_id,
            MenuMaster.isActive == True,
        ).all()
        return build_menu_tree(menus)
    return get_user_menu_tree(db, current_user.company_id, current_user.role_id)


@router.post("", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
def create_menu(
    data: MenuCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if data.parentMenuId is not None:
        parent = db.query(MenuMaster).filter(
            MenuMaster.menuId == data.parentMenuId,
            MenuMaster.companyId == current_user.company_id,
            MenuMaster.isActive == True,
        ).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Invalid parent menu")

    menu = MenuMaster(
        **data.model_dump(),
        companyId=current_user.company_id,
        createdby=current_user.user_id,
    )
    db.add(menu)
    db.commit()
    db.refresh(menu)
    return menu


@router.put("/{menu_id}", response_model=MenuResponse)
def update_menu(
    menu_id: int,
    data: MenuUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    menu = db.query(MenuMaster).filter(
        MenuMaster.menuId == menu_id,
        MenuMaster.companyId == current_user.company_id,
        MenuMaster.isActive == True,
    ).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(menu, key, value)
    menu.lastupdateby = current_user.user_id
    db.commit()
    db.refresh(menu)
    return menu


@router.delete("/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    menu = db.query(MenuMaster).filter(
        MenuMaster.menuId == menu_id,
        MenuMaster.companyId == current_user.company_id,
        MenuMaster.isActive == True,
    ).first()
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")

    menu.isActive = False
    menu.lastupdateby = current_user.user_id
    db.commit()


# --- Role-Menu Mapping ---

def _validate_role_access(db: Session, role_id: int, current_user: "CurrentUser") -> "Role":
    """Verify the caller can access this role.

    - SuperAdmins can access any active role.
    - Regular users can only access roles that belong to their active company.
    """
    if current_user.is_super_admin:
        role = db.query(Role).filter(Role.roleId == role_id, Role.isActive == True).first()
    else:
        role = db.query(Role).filter(
            Role.roleId == role_id,
            Role.companyId == current_user.company_id,
            Role.isActive == True,
        ).first()
    if not role:
        raise HTTPException(status_code=403, detail="Role not found or not accessible")
    return role


@router.get("/permission-schema")
def get_permission_schema(
    # Dependency enforces auth; the value isn't used inside the handler
    # because the schema is company-agnostic.
    _current_user: CurrentUser = Depends(get_current_user),
):
    """Declares which permission flags apply to which menus.

    Replaces the frontend-hardcoded `MENU_EXTRA_PERMS` dict. Every menu
    supports the core `canAdd / canRead / canEdit / canDelete` set;
    `extended` lists additional flags that are only meaningful for specific
    business menus (Approve/Revise on Quotations, etc.).

    Adding a new extended flag is now a one-place change: add the flag name
    here, plumb it through RoleMenuPermission + RoleMenuMap, and the UI
    picks it up automatically on next page load.
    """
    CORE = ["canAdd", "canRead", "canEdit", "canDelete"]
    # Per-menu extended perm lists. Keys match MenuMaster.menuName exactly.
    extended = {
        "Quotations": [
            "canEditNumber", "canApprove", "canRevise",
            "canTransferOwnership", "canGenerateUnderOthers",
            "canApproveAnnexure",
            # Phase 1 lifecycle flags — surfaced under Quotations menu
            # since all four lifecycle endpoints route through it.
            "canConvert", "canReactivate",
            "canSubmitPO", "canRejectPO",
            "canApproveViability",
            "canUnlockEditQuotation", "canUnlockEditPO",
            "canUnlockEditViability", "canUnlockEditAnnexure",
        ],
        "Enquiries": [
            "canEditNumber", "canApprove",
            "canTransferOwnership", "canGenerateUnderOthers",
        ],
    }
    # Human-readable labels for the flag names — served alongside so the
    # frontend doesn't need to maintain its own copy.
    labels = {
        "canAdd": "Add",
        "canRead": "Read",
        "canEdit": "Edit",
        "canDelete": "Delete",
        "canEditNumber": "Edit No.",
        "canApprove": "Approve",
        "canRevise": "Revise",
        "canTransferOwnership": "Transfer Ownership",
        "canGenerateUnderOthers": "Gen Under Others",
        "canApproveAnnexure": "Approve Annexure",
        # Phase 1 lifecycle flags
        "canConvert": "Convert",
        "canReactivate": "Reactivate",
        "canSubmitPO": "Submit & Mature PO",
        "canRejectPO": "Reject PO",
        "canApproveViability": "Approve Viability",
        "canUnlockEditQuotation": "Unlock Quotation",
        "canUnlockEditPO": "Unlock PO",
        "canUnlockEditViability": "Unlock Viability",
        "canUnlockEditAnnexure": "Unlock Annexure",
    }
    # One-line business hints used in tooltips and the preview strip.
    descriptions = {
        "canAdd": "Create new records",
        "canRead": "View records",
        "canEdit": "Modify existing records",
        "canDelete": "Soft-delete records",
        "canEditNumber": "Override the auto-generated number",
        "canApprove": "Approve a record to move it past Draft",
        "canRevise": "Create a new revision of an approved record",
        "canTransferOwnership": "Hand ownership to another user",
        "canGenerateUnderOthers": "Generate numbers using another user's code",
        "canApproveAnnexure": "Approve a quotation annexure and edit it post-approval (Commercial HOD)",
        "canConvert": "Convert an Approved quotation (forward gate to Stage 2)",
        "canReactivate": "Reactivate a Rejected quotation back to Approved",
        "canSubmitPO": "Submit & Mature the captured PO (forward gate to Stage 3)",
        "canRejectPO": "Reject a Submitted PO and un-Convert the quotation",
        "canApproveViability": "Approve the viability sheet (forward gate to Stage 4)",
        "canUnlockEditQuotation": "Privileged: edit a Converted/locked quotation in place (audited)",
        "canUnlockEditPO": "Privileged: edit a Submitted/locked PO in place (audited)",
        "canUnlockEditViability": "Privileged: edit an Approved viability sheet in place (audited)",
        "canUnlockEditAnnexure": "Privileged: edit an Approved annexure in place (audited; equivalent of CanApproveAnnexure)",
    }
    return {
        "core": CORE,
        "extended": extended,
        "labels": labels,
        "descriptions": descriptions,
    }


@router.get("/role-menu-map/{role_id}")
def get_role_menu_permissions(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _validate_role_access(db, role_id, current_user)

    menus = db.query(MenuMaster).filter(
        MenuMaster.companyId == current_user.company_id,
        MenuMaster.isActive == True,
    ).all()

    existing_mappings = db.query(RoleMenuMap).filter(
        RoleMenuMap.roleId == role_id,
        RoleMenuMap.isActive == True,
    ).all()
    mapping_dict = {m.menuId: m for m in existing_mappings}

    result = []
    for menu in menus:
        m = mapping_dict.get(menu.menuId)
        result.append({
            "menuId": menu.menuId,
            "menuName": menu.menuName,
            "parentMenuId": menu.parentMenuId,
            "menuOrder": menu.menuOrder,
            "canAdd": m.CanAdd if m else False,
            "canRead": m.CanRead if m else False,
            "canEdit": m.CanEdit if m else False,
            "canDelete": m.CanDelete if m else False,
            "canEditNumber": m.CanEditNumber if m else False,
            "canApprove": m.CanApprove if m else False,
            "canRevise": m.CanRevise if m else False,
            "canTransferOwnership": m.CanTransferOwnership if m else False,
            "canGenerateUnderOthers": m.CanGenerateUnderOthers if m else False,
            "canApproveAnnexure": m.CanApproveAnnexure if m else False,
            # Phase 1 lifecycle flags
            "canConvert": m.CanConvert if m else False,
            "canReactivate": m.CanReactivate if m else False,
            "canSubmitPO": m.CanSubmitPO if m else False,
            "canRejectPO": m.CanRejectPO if m else False,
            "canApproveViability": m.CanApproveViability if m else False,
            "canUnlockEditQuotation": m.CanUnlockEditQuotation if m else False,
            "canUnlockEditPO": m.CanUnlockEditPO if m else False,
            "canUnlockEditViability": m.CanUnlockEditViability if m else False,
            "canUnlockEditAnnexure": m.CanUnlockEditAnnexure if m else False,
        })
    return result


@router.post("/role-menu-map/{role_id}", status_code=status.HTTP_200_OK)
def save_role_menu_permissions(
    role_id: int,
    permissions: List[RoleMenuPermission],
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _validate_role_access(db, role_id, current_user)

    # ``camelCase`` flag name (UI / API) → ``PascalCase`` column name (DB).
    # Single source of truth: every flag listed here is one that round-trips
    # end-to-end. To add a new flag: add a column on RoleMenuMap (+ migration),
    # add the field to ``RoleMenuPermission`` in schemas/menu.py, and add the
    # entry here. The save handler iterates this dict — there is no other
    # place to update.
    FIELD_TO_COL = {
        "canAdd": "CanAdd",
        "canRead": "CanRead",
        "canEdit": "CanEdit",
        "canDelete": "CanDelete",
        "canEditNumber": "CanEditNumber",
        "canApprove": "CanApprove",
        "canRevise": "CanRevise",
        "canTransferOwnership": "CanTransferOwnership",
        "canGenerateUnderOthers": "CanGenerateUnderOthers",
        "canApproveAnnexure": "CanApproveAnnexure",
        # Phase 1 lifecycle flags
        "canConvert": "CanConvert",
        "canReactivate": "CanReactivate",
        "canSubmitPO": "CanSubmitPO",
        "canRejectPO": "CanRejectPO",
        "canApproveViability": "CanApproveViability",
        "canUnlockEditQuotation": "CanUnlockEditQuotation",
        "canUnlockEditPO": "CanUnlockEditPO",
        "canUnlockEditViability": "CanUnlockEditViability",
        "canUnlockEditAnnexure": "CanUnlockEditAnnexure",
    }

    # Snapshot current state BEFORE any mutation so the diff is accurate.
    existing_rows = db.query(RoleMenuMap).filter(
        RoleMenuMap.roleId == role_id,
    ).all()
    before_by_menu = {m.menuId: m for m in existing_rows}

    # Deactivate existing mappings — any menu *not* present in the request
    # body will stay deactivated. (Frontend always lists every menu it knows
    # about, so this is a no-op in practice; deactivation only matters for
    # menus that have been removed from the company.)
    db.query(RoleMenuMap).filter(
        RoleMenuMap.roleId == role_id,
    ).update({"isActive": False})

    # Upsert + collect audit deltas
    from app.core.timezone import now_ist
    from app.models.role_menu_audit import RoleMenuMapAudit
    ts = now_ist()
    audit_rows: List[RoleMenuMapAudit] = []

    # Resolve companyId once (for audit rows — role is company-scoped)
    role_obj = db.query(Role).filter(Role.roleId == role_id).first()
    company_id = role_obj.companyId if role_obj else current_user.company_id

    for perm in permissions:
        # ``exclude_unset=True`` returns ONLY the flags the caller explicitly
        # included in the request body. Pydantic distinguishes "default
        # applied" from "explicitly set", so a frontend that omits a flag
        # (because it doesn't render a checkbox for it, doesn't know about
        # it yet, or simply has a bug) will leave the existing DB value
        # alone instead of the historical silent-reset-to-False behaviour.
        # Frontends that DO send every flag (current v2 behaviour) keep
        # their full-replace semantics — every key is present, so every
        # flag gets written.
        sent: dict = perm.model_dump(exclude_unset=True)
        prev = before_by_menu.get(perm.menuId)

        if prev is not None:
            for camel, col in FIELD_TO_COL.items():
                if camel in sent:
                    setattr(prev, col, bool(sent[camel]))
            prev.isActive = True
            prev.lastupdateby = current_user.user_id
        else:
            # New row — every flag in the new row needs *some* value because
            # the columns are NOT NULL. For flags the caller didn't send we
            # default to False (matches the historical behaviour for fresh
            # menus); flags that were sent take their explicit value.
            new_kwargs = {col: False for col in FIELD_TO_COL.values()}
            for camel, col in FIELD_TO_COL.items():
                if camel in sent:
                    new_kwargs[col] = bool(sent[camel])
            db.add(RoleMenuMap(
                roleId=role_id,
                menuId=perm.menuId,
                createdby=current_user.user_id,
                **new_kwargs,
            ))

        # Audit only flags the caller actually sent — silently-preserved
        # flags didn't change, so they don't belong in the diff. For brand-
        # new rows, "default False on a flag the caller didn't send" is also
        # not a real toggle and shouldn't generate audit noise.
        for camel in FIELD_TO_COL:
            if camel not in sent:
                continue
            new_v = bool(sent[camel])
            old_v = bool(getattr(prev, FIELD_TO_COL[camel])) if prev else None
            if prev is None and new_v is False:
                continue
            if old_v != new_v:
                audit_rows.append(RoleMenuMapAudit(
                    companyId=company_id,
                    roleId=role_id,
                    menuId=perm.menuId,
                    field=FIELD_TO_COL[camel],
                    oldValue=old_v,
                    newValue=new_v,
                    changedby=current_user.user_id,
                    changedon=ts,
                ))

    for row in audit_rows:
        db.add(row)

    db.commit()

    # Invalidate permission cache for this role
    from app.services.cache_invalidation import on_role_menu_change
    on_role_menu_change(role_id)

    return {
        "message": "Permissions saved successfully",
        "auditRowsWritten": len(audit_rows),
    }


@router.get("/role-menu-map/{role_id}/audit")
def get_role_menu_audit(
    role_id: int,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Newest-first audit trail of permission changes for a role.

    Paged by a simple `limit` (default 200) — audit rows are small, and
    the UI pages via scroll if the user needs older entries.
    """
    _validate_role_access(db, role_id, current_user)
    from app.models.role_menu_audit import RoleMenuMapAudit
    from app.models.user import User
    rows = (
        db.query(
            RoleMenuMapAudit,
            MenuMaster.menuName,
            User.userName,
        )
        .join(MenuMaster, RoleMenuMapAudit.menuId == MenuMaster.menuId)
        .outerjoin(User, RoleMenuMapAudit.changedby == User.userId)
        .filter(RoleMenuMapAudit.roleId == role_id)
        .order_by(RoleMenuMapAudit.changedon.desc(), RoleMenuMapAudit.auditId.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    return [
        {
            "auditId": audit.auditId,
            "menuId": audit.menuId,
            "menuName": menu_name,
            "field": audit.field,
            "oldValue": audit.oldValue,
            "newValue": audit.newValue,
            "changedby": audit.changedby,
            "changedbyName": user_name,
            "changedon": audit.changedon,
        }
        for audit, menu_name, user_name in rows
    ]
