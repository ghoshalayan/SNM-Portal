"""Add User Location Mapping menu to all companies

Revision ID: i7j8k9l0m1n2
Revises: h6i7j8k9l0m1
Create Date: 2026-03-31 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'i7j8k9l0m1n2'
down_revision: Union[str, None] = 'h6i7j8k9l0m1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find the "Administration" parent menu per company
    admin_menus = conn.execute(
        sa.text(
            "SELECT menuId, companyId FROM MenuMaster "
            "WHERE menuName = 'Administration' AND isActive = 1"
        )
    ).fetchall()

    for admin_menu_id, company_id in admin_menus:
        # Skip if already exists
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = 'User Location Mapping' AND isActive = 1"
            ),
            {"cid": company_id},
        ).fetchone()
        if exists:
            continue

        # Determine menuOrder: place after Organization Tree (or at end)
        max_order = conn.execute(
            sa.text(
                "SELECT ISNULL(MAX(menuOrder), 0) FROM MenuMaster "
                "WHERE parentMenuId = :pid AND isActive = 1"
            ),
            {"pid": admin_menu_id},
        ).scalar()

        conn.execute(
            sa.text(
                "INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdby) "
                "VALUES (:cid, 'User Location Mapping', '/user-location-mapping', 'location_on', :pid, :ord, 1, 1)"
            ),
            {"cid": company_id, "pid": admin_menu_id, "ord": max_order + 1},
        )

        # Grant full CRUD to all active roles for this company that already have admin menu access
        new_menu_id = conn.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = 'User Location Mapping' AND isActive = 1"
            ),
            {"cid": company_id},
        ).scalar()

        if new_menu_id:
            # Find roles that have access to the Administration parent menu
            roles_with_admin = conn.execute(
                sa.text(
                    "SELECT DISTINCT roleId FROM RoleMenuMap "
                    "WHERE menuId = :mid AND isActive = 1 AND CanRead = 1"
                ),
                {"mid": admin_menu_id},
            ).fetchall()

            for (role_id,) in roles_with_admin:
                conn.execute(
                    sa.text(
                        "INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive, createdby) "
                        "VALUES (:rid, :mid, 1, 1, 1, 1, 1, 1)"
                    ),
                    {"rid": role_id, "mid": new_menu_id},
                )


def downgrade() -> None:
    conn = op.get_bind()
    # Soft-delete the menu entries
    conn.execute(
        sa.text(
            "UPDATE MenuMaster SET isActive = 0 "
            "WHERE menuName = 'User Location Mapping'"
        )
    )
