"""Remove Role-Menu Mapping submenu from sidebar (soft-delete)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-30 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Soft-delete the "Role-Menu Mapping" menu entries and their RoleMenuMap permissions
    # The menu is accessed from within Role Management, so a dedicated sidebar entry is not needed.

    # First soft-delete RoleMenuMap entries for these menus
    conn.execute(
        sa.text(
            "UPDATE RoleMenuMap SET isActive = 0 "
            "WHERE menuId IN (SELECT menuId FROM MenuMaster WHERE menuName = 'Role-Menu Mapping' AND isActive = 1)"
        )
    )

    # Then soft-delete the menu entries themselves
    conn.execute(
        sa.text(
            "UPDATE MenuMaster SET isActive = 0 "
            "WHERE menuName = 'Role-Menu Mapping' AND isActive = 1"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Re-activate the menu entries
    conn.execute(
        sa.text(
            "UPDATE MenuMaster SET isActive = 1 "
            "WHERE menuName = 'Role-Menu Mapping' AND isActive = 0"
        )
    )

    # Re-activate RoleMenuMap entries
    conn.execute(
        sa.text(
            "UPDATE RoleMenuMap SET isActive = 1 "
            "WHERE menuId IN (SELECT menuId FROM MenuMaster WHERE menuName = 'Role-Menu Mapping') "
            "AND isActive = 0"
        )
    )
