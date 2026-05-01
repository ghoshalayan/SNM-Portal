"""Add Organization Tree menu under Administration

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-30 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # For every active company, find the "Administration" parent menu and add
    # "Organization Tree" as a child.  Then grant full CRUD to every role that
    # already has access to "Role Management" (i.e. admin-level roles).

    admin_menus = conn.execute(
        sa.text(
            "SELECT menuId, companyId, createdby "
            "FROM MenuMaster "
            "WHERE menuName = 'Administration' AND isActive = 1"
        )
    ).fetchall()

    for admin_menu in admin_menus:
        parent_id = admin_menu[0]
        company_id = admin_menu[1]
        created_by = admin_menu[2]

        # Check if already exists (idempotent)
        existing = conn.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE menuName = 'Organization Tree' "
                "AND companyId = :cid AND isActive = 1"
            ),
            {"cid": company_id},
        ).fetchone()

        if existing:
            continue

        # Determine the next menuOrder under Administration
        max_order = conn.execute(
            sa.text(
                "SELECT ISNULL(MAX(menuOrder), 0) "
                "FROM MenuMaster "
                "WHERE parentMenuId = :pid AND isActive = 1"
            ),
            {"pid": parent_id},
        ).scalar()

        # Insert the new menu
        conn.execute(
            sa.text(
                "INSERT INTO MenuMaster "
                "(companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, createdby, isActive) "
                "VALUES (:cid, 'Organization Tree', '/org-tree', 'account_tree', :pid, :ord, :cb, 1)"
            ),
            {"cid": company_id, "pid": parent_id, "ord": max_order + 1, "cb": created_by},
        )

        # Get the new menuId
        new_menu_id = conn.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE menuName = 'Organization Tree' "
                "AND companyId = :cid AND isActive = 1"
            ),
            {"cid": company_id},
        ).scalar()

        # Grant permissions to all roles that have access to "Role Management"
        role_mgmt_menu = conn.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE menuName = 'Role Management' "
                "AND companyId = :cid AND isActive = 1"
            ),
            {"cid": company_id},
        ).scalar()

        if role_mgmt_menu:
            role_perms = conn.execute(
                sa.text(
                    "SELECT roleId, CanAdd, CanRead, CanEdit, CanDelete, createdby "
                    "FROM RoleMenuMap "
                    "WHERE menuId = :mid AND isActive = 1"
                ),
                {"mid": role_mgmt_menu},
            ).fetchall()

            for rp in role_perms:
                conn.execute(
                    sa.text(
                        "INSERT INTO RoleMenuMap "
                        "(roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, createdby, isActive) "
                        "VALUES (:rid, :mid, :ca, :cr, :ce, :cd, :cb, 1)"
                    ),
                    {
                        "rid": rp[0], "mid": new_menu_id,
                        "ca": rp[1], "cr": rp[2], "ce": rp[3], "cd": rp[4],
                        "cb": rp[5],
                    },
                )


def downgrade() -> None:
    conn = op.get_bind()

    # Remove RoleMenuMap entries for Organization Tree
    conn.execute(
        sa.text(
            "UPDATE RoleMenuMap SET isActive = 0 "
            "WHERE menuId IN ("
            "  SELECT menuId FROM MenuMaster "
            "  WHERE menuName = 'Organization Tree' AND isActive = 1"
            ")"
        )
    )

    # Soft-delete the menu entries
    conn.execute(
        sa.text(
            "UPDATE MenuMaster SET isActive = 0 "
            "WHERE menuName = 'Organization Tree' AND isActive = 1"
        )
    )
