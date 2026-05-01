"""Add Settings submenu under KPI Studio (Phase A7+)

For each company that already has a KPI Studio parent menu (seeded by
``z0a1b2c3d4e5_add_kpi_studio_menus``), append a "Settings" submenu
pointing at /kpi-studio/settings and grant SuperAdmin role(s) full
CRUD on it. Idempotent — safe to re-run.

Revision ID: e5f6h7i8j9k0
Revises: d4e5f6h7i8j9
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


revision: str = "e5f6h7i8j9k0"
down_revision: Union[str, None] = "d4e5f6h7i8j9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHILD = {
    "name": "Settings",
    "url": "/kpi-studio/settings",
    "icon": "settings",
    "order": 4,
}


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    # Find every KPI Studio parent menu that's already in place. If a
    # company never got the parent (z0a1b2c3d4e5 not run for them), skip
    # — the parent migration is the prerequisite.
    parents = session.execute(sa.text(
        "SELECT menuId, companyId FROM MenuMaster "
        "WHERE menuName = 'KPI Studio' AND parentMenuId IS NULL "
        "AND isActive = 1"
    )).fetchall()

    for parent_id, company_id in parents:
        # Skip if Settings already exists for this parent.
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

        # Grant full CRUD to all SuperAdmin roles in this company.
        superadmin_role_ids = [
            row[0] for row in session.execute(sa.text(
                "SELECT roleId FROM RoleMaster "
                "WHERE companyId = :cid AND IsSuperAdmin = 1 AND isActive = 1"
            ), {"cid": company_id}).fetchall()
        ]
        for role_id in superadmin_role_ids:
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

    # Remove role grants first (FK direction).
    session.execute(sa.text(
        "DELETE FROM RoleMenuMap WHERE menuId IN ("
        "  SELECT menuId FROM MenuMaster WHERE menuUrl = '/kpi-studio/settings'"
        ")"
    ))
    session.execute(sa.text(
        "DELETE FROM MenuMaster WHERE menuUrl = '/kpi-studio/settings'"
    ))
    session.commit()
