"""Seeds default menus, roles, and permissions when a new company is created."""

from sqlalchemy.orm import Session

from app.models.menu import MenuMaster
from app.models.role import Role
from app.models.role_menu_map import RoleMenuMap
from app.models.user import UserRoleMap


# Canonical menu tree — matches frontend route paths (plural slugs)
DEFAULT_MENU_TREE = [
    ("Dashboard", "/dashboard", "dashboard", []),
    ("Administration", None, "admin_panel_settings", [
        ("Company Management", "/companies", "business", []),
        ("User Management", "/users", "people", []),
        ("Role Management", "/roles", "security", []),
        ("User Location Mapping", "/user-location-mapping", "location_on", []),
        ("Organization Tree", "/org-tree", "account_tree", []),
    ]),
    ("Masters", None, "settings", [
        ("Item Grade", "/masters/item-grades", "grade", []),
        ("Item Name", "/masters/item-names", "inventory_2", []),
        ("Item Length", "/masters/item-lengths", "straighten", []),
        ("Item Size", "/masters/item-sizes", "aspect_ratio", []),
        ("Delivery Term", "/masters/delivery-terms", "local_shipping", []),
        ("Delivery Mode", "/masters/delivery-modes", "commute", []),
        ("Contact Type", "/masters/contact-types", "contact_phone", []),
        ("Customer Classification", "/masters/customer-classifications", "category", []),
        ("Cost Point", "/masters/cost-points", "monetization_on", []),
        ("Terms & Conditions", "/masters/terms-conditions", "gavel", []),
        ("Raw Material Cost", "/masters/raw-material-costs", "attach_money", []),
        ("Country", "/masters/countries", "public", []),
        ("State", "/masters/states", "map", []),
        ("District", "/masters/districts", "location_city", []),
        ("Dia Master", "/masters/dia-masters", "radio_button_unchecked", []),
        ("Enquiry Status", "/masters/enq-statuses", "flag", []),
        ("Quotation Status", "/masters/quot-statuses", "bookmark", []),
        ("Communication Mode", "/masters/communication-modes", "sms", []),
    ]),
    ("Customers", None, "groups", [
        ("Customer List", "/customers", "list", []),
    ]),
    ("Enquiries", None, "request_quote", [
        ("Enquiry List", "/enquiries", "list_alt", []),
    ]),
    ("Quotations", None, "description", [
        ("Quotation List", "/quotations", "format_list_numbered", []),
    ]),
    ("Assets", None, "cloud_upload", [
        ("Quotation Formats", "/assets/quotation-formats", "article", []),
    ]),
    ("Logs", None, "history", [
        ("Communication Logs", "/communication-logs", "chat", []),
    ]),
]


def _insert_menus(
    db: Session,
    company_id: int,
    menus: list,
    parent_id: int | None,
    order_start: int,
    created_by: int,
) -> list[int]:
    """Recursively insert menus, return all inserted menu IDs."""
    all_ids = []
    for idx, (name, url, icon, children) in enumerate(menus):
        menu = MenuMaster(
            companyId=company_id,
            menuName=name,
            menuUrl=url,
            menuIcon=icon,
            parentMenuId=parent_id,
            menuOrder=order_start + idx,
            createdby=created_by,
        )
        db.add(menu)
        db.flush()  # get menuId
        all_ids.append(menu.menuId)
        if children:
            child_ids = _insert_menus(db, company_id, children, menu.menuId, 1, created_by)
            all_ids.extend(child_ids)
    return all_ids


def seed_company_defaults(db: Session, company_id: int, created_by: int) -> None:
    """Seed default menus, an admin role, and full permissions for a new company.

    Called after a new company is created. Does NOT commit — caller handles the transaction.
    """
    # 1a. Create a SuperAdmin role for this company
    sa_role = Role(
        companyId=company_id,
        roleName="Super Admin",
        IsSuperAdmin=True,
        createdby=created_by,
    )
    db.add(sa_role)
    db.flush()

    # 1b. Create a default Admin role for this company
    admin_role = Role(
        companyId=company_id,
        roleName="Admin",
        IsSuperAdmin=False,
        createdby=created_by,
    )
    db.add(admin_role)
    db.flush()

    # 2. Insert full menu tree
    all_menu_ids = _insert_menus(db, company_id, DEFAULT_MENU_TREE, None, 1, created_by)

    # 3. Grant full CRUD on all menus to Admin and SuperAdmin roles
    for role in [sa_role, admin_role]:
        for mid in all_menu_ids:
            db.add(RoleMenuMap(
                roleId=role.roleId,
                menuId=mid,
                CanAdd=True,
                CanRead=True,
                CanEdit=True,
                CanDelete=True,
                createdby=created_by,
            ))

    # 4. Map all existing SuperAdmin users to this company with the SA role
    sa_user_ids = (
        db.query(UserRoleMap.userId)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(Role.IsSuperAdmin == True, UserRoleMap.isActive == True)
        .distinct()
        .all()
    )
    for (uid,) in sa_user_ids:
        # Skip if already mapped to this company
        exists = db.query(UserRoleMap).filter(
            UserRoleMap.userId == uid,
            UserRoleMap.companyId == company_id,
        ).first()
        if not exists:
            db.add(UserRoleMap(
                userId=uid,
                roleId=sa_role.roleId,
                companyId=company_id,
                isDefault=False,
                createdby=created_by,
            ))

    db.flush()


def seed_superadmin_for_all_companies(db: Session, created_by: int) -> dict:
    """Backfill: ensure every active company has a SuperAdmin role and all SA users are mapped.

    Safe to run multiple times — skips companies that already have a SuperAdmin role.
    Does NOT commit — caller handles the transaction.
    """
    from app.models.company import Company

    companies = db.query(Company).filter(Company.isActive == True).all()

    # Find all SuperAdmin user IDs
    sa_user_ids = (
        db.query(UserRoleMap.userId)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(Role.IsSuperAdmin == True, UserRoleMap.isActive == True)
        .distinct()
        .all()
    )
    sa_uids = [uid for (uid,) in sa_user_ids]

    roles_created = 0
    mappings_created = 0

    for company in companies:
        # Ensure SuperAdmin role exists
        sa_role = db.query(Role).filter(
            Role.companyId == company.companyId,
            Role.IsSuperAdmin == True,
            Role.isActive == True,
        ).first()

        if not sa_role:
            sa_role = Role(
                companyId=company.companyId,
                roleName="Super Admin",
                IsSuperAdmin=True,
                createdby=created_by,
            )
            db.add(sa_role)
            db.flush()

            # Grant full CRUD on all company menus
            menus = db.query(MenuMaster).filter(
                MenuMaster.companyId == company.companyId,
                MenuMaster.isActive == True,
            ).all()
            for menu in menus:
                db.add(RoleMenuMap(
                    roleId=sa_role.roleId,
                    menuId=menu.menuId,
                    CanAdd=True, CanRead=True, CanEdit=True, CanDelete=True,
                    createdby=created_by,
                ))
            roles_created += 1

        # Map all SA users to this company
        for uid in sa_uids:
            exists = db.query(UserRoleMap).filter(
                UserRoleMap.userId == uid,
                UserRoleMap.companyId == company.companyId,
            ).first()
            if not exists:
                db.add(UserRoleMap(
                    userId=uid,
                    roleId=sa_role.roleId,
                    companyId=company.companyId,
                    isDefault=False,
                    createdby=created_by,
                ))
                mappings_created += 1

    db.flush()
    return {"roles_created": roles_created, "mappings_created": mappings_created}
