"""Add Financial Years submenu under Masters for existing companies

Revision ID: w1x2y3z4a5b6
Revises: v0w1x2y3z4a5
Create Date: 2026-04-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


revision: str = "w1x2y3z4a5b6"
down_revision: Union[str, None] = "v0w1x2y3z4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    # Find all "Masters" parent menus (one per company)
    masters_menus = session.execute(
        sa.text(
            "SELECT menuId, companyId FROM MenuMaster "
            "WHERE menuName = 'Masters' AND isActive = 1"
        )
    ).fetchall()

    for masters_menu_id, company_id in masters_menus:
        # Get the next sort order
        max_order = session.execute(
            sa.text(
                "SELECT ISNULL(MAX(menuOrder), 0) FROM MenuMaster "
                "WHERE parentMenuId = :pid AND companyId = :cid"
            ),
            {"pid": masters_menu_id, "cid": company_id},
        ).scalar()

        # Insert Financial Years submenu
        session.execute(
            sa.text(
                "INSERT INTO MenuMaster "
                "(companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive) "
                "VALUES (:cid, 'Financial Years', '/masters/financial-years', 'calendar_today', :pid, :ord, 1)"
            ),
            {"cid": company_id, "pid": masters_menu_id, "ord": (max_order or 0) + 1},
        )

        # Get the new submenu ID
        new_menu = session.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = 'Financial Years' AND parentMenuId = :pid"
            ),
            {"cid": company_id, "pid": masters_menu_id},
        ).fetchone()

        if new_menu:
            new_menu_id = new_menu[0]
            # Copy permissions from parent Masters menu
            existing_perms = session.execute(
                sa.text(
                    "SELECT roleId, canAdd, canRead, canEdit, canDelete "
                    "FROM RoleMenuMap WHERE menuId = :mid AND isActive = 1"
                ),
                {"mid": masters_menu_id},
            ).fetchall()

            for role_id, can_add, can_read, can_edit, can_delete in existing_perms:
                session.execute(
                    sa.text(
                        "INSERT INTO RoleMenuMap "
                        "(roleId, menuId, canAdd, canRead, canEdit, canDelete, isActive) "
                        "VALUES (:rid, :mid, :a, :r, :e, :d, 1)"
                    ),
                    {"rid": role_id, "mid": new_menu_id,
                     "a": can_add, "r": can_read, "e": can_edit, "d": can_delete},
                )

    session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    session.execute(
        sa.text(
            "DELETE FROM RoleMenuMap WHERE menuId IN "
            "(SELECT menuId FROM MenuMaster WHERE menuName = 'Financial Years' "
            "AND menuUrl = '/masters/financial-years')"
        )
    )
    session.execute(
        sa.text(
            "DELETE FROM MenuMaster WHERE menuName = 'Financial Years' "
            "AND menuUrl = '/masters/financial-years'"
        )
    )

    session.commit()
