"""Seed superadmin, test user, company, menus, permissions

Revision ID: e88c297e3e9d
Revises: 9eaf9699f05f
Create Date: 2026-03-28 18:16:57.902229

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision: str = 'e88c297e3e9d'
down_revision: Union[str, None] = '9eaf9699f05f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = datetime.utcnow()

# Pre-hashed passwords (bcrypt)
ADMIN_PASSWORD_HASH = "$2b$12$Y5420y.ndEwxszWACVeYfug6U9ifs71r8vihJps9VQPpauYKPm9u6"  # Admin@123
TEST_PASSWORD_HASH = "$2b$12$fCY8samkx1FF.nk55aZ48untQta1ZYW1f9N1VVePdlGdWdz.oEnhG"   # Test@123

# Menu tree structure: (menuName, menuUrl, menuIcon, children[])
MENU_TREE = [
    ("Dashboard", "/dashboard", "dashboard", []),
    ("Administration", None, "admin_panel_settings", [
        ("Company Management", "/companies", "business", []),
        ("User Management", "/users", "people", []),
        ("Role Management", "/roles", "security", []),
        ("Role-Menu Mapping", "/roles/menu-mapping", "assignment", []),
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
    ("Assets", "/assets", "cloud_upload", []),
]


def _insert_menus(conn, company_id, menus, parent_id, order_start, created_by):
    """Recursively insert menus and return list of all inserted menu IDs."""
    all_menu_ids = []
    for idx, (name, url, icon, children) in enumerate(menus):
        result = conn.execute(
            sa.text(
                "INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, "
                "isActive, createdon, createdby) "
                "OUTPUT INSERTED.menuId "
                "VALUES (:cid, :name, :url, :icon, :pid, :ord, 1, :now, :cb)"
            ),
            {
                "cid": company_id, "name": name, "url": url, "icon": icon,
                "pid": parent_id, "ord": order_start + idx, "now": NOW, "cb": created_by,
            },
        )
        menu_id = result.scalar()
        all_menu_ids.append(menu_id)
        if children:
            child_ids = _insert_menus(conn, company_id, children, menu_id, 1, created_by)
            all_menu_ids.extend(child_ids)
    return all_menu_ids


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Seed Company
    result = conn.execute(
        sa.text(
            "INSERT INTO Company (companyName, companyCode, city, state, country, isActive, createdon, createdby) "
            "OUTPUT INSERTED.companyId "
            "VALUES (:name, :code, :city, :state, :country, 1, :now, 1)"
        ),
        {"name": "SNM Default Company", "code": "SNM", "city": "Mumbai",
         "state": "Maharashtra", "country": "India", "now": NOW},
    )
    company_id = result.scalar()

    # 2. Seed SuperAdmin Role
    result = conn.execute(
        sa.text(
            "INSERT INTO RoleMaster (companyId, roleName, IsSuperAdmin, isActive, createdon, createdby) "
            "OUTPUT INSERTED.roleId "
            "VALUES (:cid, :name, 1, 1, :now, 1)"
        ),
        {"cid": company_id, "name": "Super Admin", "now": NOW},
    )
    admin_role_id = result.scalar()

    # 3. Seed Standard User Role
    result = conn.execute(
        sa.text(
            "INSERT INTO RoleMaster (companyId, roleName, IsSuperAdmin, isActive, createdon, createdby) "
            "OUTPUT INSERTED.roleId "
            "VALUES (:cid, :name, 0, 1, :now, 1)"
        ),
        {"cid": company_id, "name": "Standard User", "now": NOW},
    )
    user_role_id = result.scalar()

    # 4. Seed SuperAdmin User
    result = conn.execute(
        sa.text(
            "INSERT INTO UserMaster (companyId, userName, userCode, userEmail, userLogin, userPassword, "
            "isActive, createdon, createdby) "
            "OUTPUT INSERTED.userId "
            "VALUES (:cid, :name, :code, :email, :login, :pwd, 1, :now, 1)"
        ),
        {"cid": company_id, "name": "Super Administrator", "code": "SADMIN",
         "email": "admin@snm.com", "login": "admin", "pwd": ADMIN_PASSWORD_HASH, "now": NOW},
    )
    admin_user_id = result.scalar()

    # 5. Seed Test User
    result = conn.execute(
        sa.text(
            "INSERT INTO UserMaster (companyId, userName, userCode, userEmail, userLogin, userPassword, "
            "isActive, createdon, createdby) "
            "OUTPUT INSERTED.userId "
            "VALUES (:cid, :name, :code, :email, :login, :pwd, 1, :now, :cb)"
        ),
        {"cid": company_id, "name": "Test User", "code": "TUSER",
         "email": "test@snm.com", "login": "testuser", "pwd": TEST_PASSWORD_HASH,
         "now": NOW, "cb": admin_user_id},
    )
    test_user_id = result.scalar()

    # 6. UserRoleMap — admin → Super Admin, test → Standard User
    conn.execute(
        sa.text(
            "INSERT INTO UserRoleMap (userId, roleId, companyId, isDefault, isActive, createdon, createdby) "
            "VALUES (:uid, :rid, :cid, 1, 1, :now, :cb)"
        ),
        {"uid": admin_user_id, "rid": admin_role_id, "cid": company_id, "now": NOW, "cb": admin_user_id},
    )
    conn.execute(
        sa.text(
            "INSERT INTO UserRoleMap (userId, roleId, companyId, isDefault, isActive, createdon, createdby) "
            "VALUES (:uid, :rid, :cid, 1, 1, :now, :cb)"
        ),
        {"uid": test_user_id, "rid": user_role_id, "cid": company_id, "now": NOW, "cb": admin_user_id},
    )

    # 7. Insert full menu tree
    all_menu_ids = _insert_menus(conn, company_id, MENU_TREE, None, 1, admin_user_id)

    # 8. RoleMenuMap — SuperAdmin gets full CRUD on ALL menus
    for mid in all_menu_ids:
        conn.execute(
            sa.text(
                "INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, "
                "isActive, createdon, createdby) "
                "VALUES (:rid, :mid, 1, 1, 1, 1, 1, :now, :cb)"
            ),
            {"rid": admin_role_id, "mid": mid, "now": NOW, "cb": admin_user_id},
        )

    # 9. RoleMenuMap — Standard User gets read-only on Dashboard, Customers, Enquiries, Quotations
    #    and full CRUD on Enquiries and Quotations detail pages
    # First, find menu IDs by name for targeted permissions
    read_only_names = {"Dashboard", "Customers", "Customer List"}
    full_crud_names = {"Enquiries", "Enquiry List", "Quotations", "Quotation List", "Assets"}

    for mid in all_menu_ids:
        row = conn.execute(
            sa.text("SELECT menuName FROM MenuMaster WHERE menuId = :mid"),
            {"mid": mid},
        ).first()
        if not row:
            continue
        menu_name = row[0]

        if menu_name in read_only_names:
            conn.execute(
                sa.text(
                    "INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, "
                    "isActive, createdon, createdby) "
                    "VALUES (:rid, :mid, 0, 1, 0, 0, 1, :now, :cb)"
                ),
                {"rid": user_role_id, "mid": mid, "now": NOW, "cb": admin_user_id},
            )
        elif menu_name in full_crud_names:
            conn.execute(
                sa.text(
                    "INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, "
                    "isActive, createdon, createdby) "
                    "VALUES (:rid, :mid, 1, 1, 1, 1, 1, :now, :cb)"
                ),
                {"rid": user_role_id, "mid": mid, "now": NOW, "cb": admin_user_id},
            )


def downgrade() -> None:
    # Intentionally a no-op.
    #
    # The original downgrade ran unscoped `DELETE FROM` statements on
    # RoleMenuMap, UserRoleMap, MenuMaster, UserMaster, RoleMaster and
    # Company — wiping ALL tenant data, not just the seeded rows. Running
    # `alembic downgrade` in production (even accidentally) would nuke the
    # platform.
    #
    # If you genuinely need to unwind the seed rows, do it manually with
    # targeted deletes scoped to the seeded IDs — there is no safe
    # generic rollback for a seed migration.
    raise RuntimeError(
        "Downgrading the initial seed migration is disabled — it would "
        "delete all tenant data. Unwind the seeded rows manually if needed."
    )
