"""Add Smart Analysis (chatbot) submenu under KPI Studio (Phase B1)

For each company that has a KPI Studio parent menu (seeded by
``z0a1b2c3d4e5_add_kpi_studio_menus``), append a "Smart Analysis"
submenu pointing at /kpi-studio/chat. Granted to SuperAdmin roles
only — non-SuperAdmin still access dashboards from /dashboard tiles
and don't see KPI Studio in the sidebar.

Revision ID: g7h8i9j0k1l2
Revises: f6h7i8j9k0l1
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6h7i8j9k0l1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHILD = {
    "name": "Smart Analysis",
    "url": "/kpi-studio/chat",
    "icon": "smart_toy",
    "order": 5,
}


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    parents = session.execute(sa.text(
        "SELECT menuId, companyId FROM MenuMaster "
        "WHERE menuName = 'KPI Studio' AND parentMenuId IS NULL "
        "AND isActive = 1"
    )).fetchall()

    for parent_id, company_id in parents:
        existing = session.execute(sa.text(
            "SELECT menuId FROM MenuMaster "
            "WHERE companyId = :cid AND menuName = :name AND parentMenuId = :pid"
        ), {"cid": company_id, "name": CHILD["name"], "pid": parent_id}).fetchone()

        if existing:
            child_id = existing[0]
        else:
            session.execute(sa.text(
                """INSERT INTO MenuMaster
                   (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive)
                   VALUES (:cid, :name, :url, :icon, :pid, :order, 1)"""
            ), {
                "cid": company_id,
                "name": CHILD["name"],
                "url": CHILD["url"],
                "icon": CHILD["icon"],
                "pid": parent_id,
                "order": CHILD["order"],
            })
            child_id = session.execute(sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = :name AND parentMenuId = :pid"
            ), {"cid": company_id, "name": CHILD["name"], "pid": parent_id}).scalar()

        # Grant SuperAdmin roles full CRUD on this menu.
        for (role_id,) in session.execute(sa.text(
            "SELECT roleId FROM RoleMaster "
            "WHERE companyId = :cid AND IsSuperAdmin = 1 AND isActive = 1"
        ), {"cid": company_id}).fetchall():
            already = session.execute(sa.text(
                "SELECT 1 FROM RoleMenuMap WHERE roleId = :rid AND menuId = :mid"
            ), {"rid": role_id, "mid": child_id}).fetchone()
            if already:
                continue
            session.execute(sa.text(
                """INSERT INTO RoleMenuMap
                   (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive)
                   VALUES (:rid, :mid, 1, 1, 1, 1, 1)"""
            ), {"rid": role_id, "mid": child_id})

    session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute(sa.text(
        "DELETE FROM RoleMenuMap WHERE menuId IN ("
        "  SELECT menuId FROM MenuMaster WHERE menuUrl = '/kpi-studio/chat'"
        ")"
    ))
    session.execute(sa.text(
        "DELETE FROM MenuMaster WHERE menuUrl = '/kpi-studio/chat'"
    ))
    session.commit()
