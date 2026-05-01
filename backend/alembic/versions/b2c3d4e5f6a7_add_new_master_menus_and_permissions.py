"""Add Country, State, District, Dia Master menus and Super Admin permissions

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-29 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = datetime.utcnow()

# New master menus to add under the existing "Masters" parent menu
NEW_MENUS = [
    ("Country", "/masters/countries", "public"),
    ("State", "/masters/states", "map"),
    ("District", "/masters/districts", "location_city"),
    ("Dia Master", "/masters/dia-masters", "radio_button_unchecked"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # For each company, find the "Masters" parent menu and the Super Admin role,
    # then insert the new menus and grant full CRUD permissions.
    companies = conn.execute(sa.text("SELECT companyId FROM Company WHERE isActive = 1")).fetchall()

    for (company_id,) in companies:
        # Find the "Masters" parent menu for this company
        row = conn.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = 'Masters' AND parentMenuId IS NULL AND isActive = 1"
            ),
            {"cid": company_id},
        ).first()
        if not row:
            continue
        masters_menu_id = row[0]

        # Find the current max menuOrder under Masters
        max_order_row = conn.execute(
            sa.text(
                "SELECT ISNULL(MAX(menuOrder), 0) FROM MenuMaster "
                "WHERE companyId = :cid AND parentMenuId = :pid AND isActive = 1"
            ),
            {"cid": company_id, "pid": masters_menu_id},
        ).first()
        next_order = (max_order_row[0] if max_order_row else 0) + 1

        # Find all roles for this company that have IsSuperAdmin = 1
        admin_roles = conn.execute(
            sa.text(
                "SELECT roleId FROM RoleMaster WHERE companyId = :cid AND IsSuperAdmin = 1 AND isActive = 1"
            ),
            {"cid": company_id},
        ).fetchall()

        # Find the admin user (createdby) — use the first super admin user for audit fields
        admin_user_row = conn.execute(
            sa.text(
                "SELECT TOP 1 u.userId FROM UserMaster u "
                "INNER JOIN UserRoleMap urm ON u.userId = urm.userId "
                "INNER JOIN RoleMaster r ON urm.roleId = r.roleId "
                "WHERE r.companyId = :cid AND r.IsSuperAdmin = 1 AND u.isActive = 1"
            ),
            {"cid": company_id},
        ).first()
        created_by = admin_user_row[0] if admin_user_row else 1

        # Insert each new menu
        for idx, (name, url, icon) in enumerate(NEW_MENUS):
            # Check if this menu already exists (idempotent)
            existing = conn.execute(
                sa.text(
                    "SELECT menuId FROM MenuMaster "
                    "WHERE companyId = :cid AND menuName = :name AND parentMenuId = :pid AND isActive = 1"
                ),
                {"cid": company_id, "name": name, "pid": masters_menu_id},
            ).first()

            if existing:
                menu_id = existing[0]
            else:
                result = conn.execute(
                    sa.text(
                        "INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, "
                        "isActive, createdon, createdby) "
                        "OUTPUT INSERTED.menuId "
                        "VALUES (:cid, :name, :url, :icon, :pid, :ord, 1, :now, :cb)"
                    ),
                    {
                        "cid": company_id, "name": name, "url": url, "icon": icon,
                        "pid": masters_menu_id, "ord": next_order + idx, "now": NOW, "cb": created_by,
                    },
                )
                menu_id = result.scalar()

            # Grant full CRUD to all Super Admin roles for this company
            for (role_id,) in admin_roles:
                # Check if mapping already exists
                existing_map = conn.execute(
                    sa.text(
                        "SELECT roleMenuMapId FROM RoleMenuMap "
                        "WHERE roleId = :rid AND menuId = :mid AND isActive = 1"
                    ),
                    {"rid": role_id, "mid": menu_id},
                ).first()

                if not existing_map:
                    conn.execute(
                        sa.text(
                            "INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, "
                            "isActive, createdon, createdby) "
                            "VALUES (:rid, :mid, 1, 1, 1, 1, 1, :now, :cb)"
                        ),
                        {"rid": role_id, "mid": menu_id, "now": NOW, "cb": created_by},
                    )


def downgrade() -> None:
    conn = op.get_bind()
    menu_names = ("Country", "State", "District", "Dia Master")
    for name in menu_names:
        # Delete role-menu mappings for these menus
        conn.execute(
            sa.text(
                "DELETE FROM RoleMenuMap WHERE menuId IN "
                "(SELECT menuId FROM MenuMaster WHERE menuName = :name)"
            ),
            {"name": name},
        )
        # Delete the menu entries
        conn.execute(
            sa.text("DELETE FROM MenuMaster WHERE menuName = :name"),
            {"name": name},
        )
