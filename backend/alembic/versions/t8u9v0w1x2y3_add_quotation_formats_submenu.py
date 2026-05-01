"""Add Quotation Formats submenu under Assets for existing companies

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-04-03 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = "t8u9v0w1x2y3"
down_revision: Union[str, None] = "s7t8u9v0w1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    # Find all existing "Assets" menus (one per company)
    result = session.execute(
        sa.text(
            "SELECT menuId, companyId FROM MenuMaster WHERE menuName = 'Assets' AND isActive = 1"
        )
    )
    assets_menus = result.fetchall()

    for assets_menu_id, company_id in assets_menus:
        # Make Assets a parent menu (clear its URL so it becomes expandable)
        session.execute(
            sa.text("UPDATE MenuMaster SET menuUrl = NULL WHERE menuId = :mid"),
            {"mid": assets_menu_id},
        )

        # Insert Quotation Formats submenu
        session.execute(
            sa.text(
                """INSERT INTO MenuMaster
                   (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive)
                   VALUES (:cid, 'Quotation Formats', '/assets/quotation-formats', 'article', :pid, 1, 1)"""
            ),
            {"cid": company_id, "pid": assets_menu_id},
        )

        # Get the new submenu's ID
        new_menu = session.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster WHERE companyId = :cid AND menuName = 'Quotation Formats' AND parentMenuId = :pid"
            ),
            {"cid": company_id, "pid": assets_menu_id},
        ).fetchone()

        if new_menu:
            new_menu_id = new_menu[0]
            # Grant full CRUD to all roles that have access to the parent Assets menu
            existing_perms = session.execute(
                sa.text(
                    "SELECT roleId FROM RoleMenuMap WHERE menuId = :mid AND isActive = 1"
                ),
                {"mid": assets_menu_id},
            ).fetchall()

            for (role_id,) in existing_perms:
                session.execute(
                    sa.text(
                        """INSERT INTO RoleMenuMap
                           (roleId, menuId, canAdd, canRead, canEdit, canDelete, isActive)
                           VALUES (:rid, :mid, 1, 1, 1, 1, 1)"""
                    ),
                    {"rid": role_id, "mid": new_menu_id},
                )

    session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    # Remove Quotation Formats submenus
    session.execute(
        sa.text(
            "DELETE FROM RoleMenuMap WHERE menuId IN (SELECT menuId FROM MenuMaster WHERE menuName = 'Quotation Formats' AND menuUrl = '/assets/quotation-formats')"
        )
    )
    session.execute(
        sa.text(
            "DELETE FROM MenuMaster WHERE menuName = 'Quotation Formats' AND menuUrl = '/assets/quotation-formats'"
        )
    )

    # Restore Assets as a leaf menu
    session.execute(
        sa.text(
            "UPDATE MenuMaster SET menuUrl = '/assets' WHERE menuName = 'Assets' AND isActive = 1"
        )
    )

    session.commit()
