"""Seed KPI Studio menu + submenus and grant SuperAdmin permissions

Adds, per existing company:
  * Parent menu: "KPI Studio"
  * Children:
      - "Dashboards"      → /kpi-studio/dashboards
      - "KPIs"            → /kpi-studio/kpis
      - "Schema Explorer" → /kpi-studio/schema  (SuperAdmin diagnostic)

Grants full CRUD permissions on every new menu to all roles flagged
``IsSuperAdmin = 1``. Idempotent — re-running detects existing entries
and skips. Designed to be safe to apply on production data.

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


revision: str = "z0a1b2c3d4e5"
down_revision: Union[str, None] = "y9z0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Order matters for menuOrder + display: parent first, then children in
# the order users should see them in the sidebar.
PARENT_MENU = {
    "name": "KPI Studio",
    "icon": "insights",
}

CHILD_MENUS = [
    {"name": "Dashboards",      "url": "/kpi-studio/dashboards", "icon": "space_dashboard", "order": 1},
    {"name": "KPIs",            "url": "/kpi-studio/kpis",       "icon": "monitoring",      "order": 2},
    {"name": "Schema Explorer", "url": "/kpi-studio/schema",     "icon": "schema",          "order": 3},
]


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    # Discover companies + the "next" menuOrder slot per company so the
    # parent menu appears below existing top-level entries.
    companies = session.execute(
        sa.text("SELECT companyId FROM Company WHERE isActive = 1")
    ).fetchall()

    for (company_id,) in companies:
        # Skip if parent already exists (idempotent).
        existing_parent = session.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = :name AND parentMenuId IS NULL"
            ),
            {"cid": company_id, "name": PARENT_MENU["name"]},
        ).fetchone()

        if existing_parent:
            parent_id = existing_parent[0]
        else:
            next_order = session.execute(
                sa.text(
                    "SELECT COALESCE(MAX(menuOrder), 0) + 1 FROM MenuMaster "
                    "WHERE companyId = :cid AND parentMenuId IS NULL"
                ),
                {"cid": company_id},
            ).scalar() or 1

            session.execute(
                sa.text(
                    """INSERT INTO MenuMaster
                       (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive)
                       VALUES (:cid, :name, NULL, :icon, NULL, :order, 1)"""
                ),
                {
                    "cid": company_id,
                    "name": PARENT_MENU["name"],
                    "icon": PARENT_MENU["icon"],
                    "order": next_order,
                },
            )
            parent_id = session.execute(
                sa.text(
                    "SELECT menuId FROM MenuMaster "
                    "WHERE companyId = :cid AND menuName = :name AND parentMenuId IS NULL"
                ),
                {"cid": company_id, "name": PARENT_MENU["name"]},
            ).scalar()

        # Find SuperAdmin role(s) for this company. There can be more than
        # one if the company has both a global-bypass SuperAdmin and an
        # alternate SuperAdmin template.
        superadmin_role_ids = [
            row[0] for row in session.execute(
                sa.text(
                    "SELECT roleId FROM RoleMaster "
                    "WHERE companyId = :cid AND IsSuperAdmin = 1 AND isActive = 1"
                ),
                {"cid": company_id},
            ).fetchall()
        ]

        # Insert child menus + grant SuperAdmin full CRUD on each.
        for child in CHILD_MENUS:
            existing_child = session.execute(
                sa.text(
                    "SELECT menuId FROM MenuMaster "
                    "WHERE companyId = :cid AND menuName = :name AND parentMenuId = :pid"
                ),
                {"cid": company_id, "name": child["name"], "pid": parent_id},
            ).fetchone()

            if existing_child:
                child_id = existing_child[0]
            else:
                session.execute(
                    sa.text(
                        """INSERT INTO MenuMaster
                           (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive)
                           VALUES (:cid, :name, :url, :icon, :pid, :order, 1)"""
                    ),
                    {
                        "cid": company_id,
                        "name": child["name"],
                        "url": child["url"],
                        "icon": child["icon"],
                        "pid": parent_id,
                        "order": child["order"],
                    },
                )
                child_id = session.execute(
                    sa.text(
                        "SELECT menuId FROM MenuMaster "
                        "WHERE companyId = :cid AND menuName = :name AND parentMenuId = :pid"
                    ),
                    {"cid": company_id, "name": child["name"], "pid": parent_id},
                ).scalar()

            for role_id in superadmin_role_ids:
                _grant(session, role_id, child_id, full=True)

        # Parent itself only needs CanRead so the sidebar tree builds —
        # the URL is null, so CRUD flags are irrelevant.
        for role_id in superadmin_role_ids:
            _grant(session, role_id, parent_id, full=False)

    session.commit()


def downgrade() -> None:
    """Remove KPI Studio menu rows + their permission grants.

    Targets specifically by URL prefix + parent name so we don't disturb
    any user-renamed entries that happen to share names.
    """
    bind = op.get_bind()
    session = Session(bind=bind)

    # Children first (FK direction).
    session.execute(
        sa.text(
            "DELETE FROM RoleMenuMap WHERE menuId IN ("
            "  SELECT menuId FROM MenuMaster "
            "  WHERE menuUrl LIKE '/kpi-studio/%'"
            ")"
        )
    )
    session.execute(
        sa.text("DELETE FROM MenuMaster WHERE menuUrl LIKE '/kpi-studio/%'")
    )

    # Then the parent (no URL, identified by name + null parent).
    session.execute(
        sa.text(
            "DELETE FROM RoleMenuMap WHERE menuId IN ("
            "  SELECT menuId FROM MenuMaster "
            "  WHERE menuName = 'KPI Studio' AND parentMenuId IS NULL"
            ")"
        )
    )
    session.execute(
        sa.text(
            "DELETE FROM MenuMaster "
            "WHERE menuName = 'KPI Studio' AND parentMenuId IS NULL"
        )
    )

    session.commit()


def _grant(session: Session, role_id: int, menu_id: int, *, full: bool) -> None:
    """Insert a RoleMenuMap row if missing; idempotent."""
    exists = session.execute(
        sa.text(
            "SELECT 1 FROM RoleMenuMap "
            "WHERE roleId = :rid AND menuId = :mid"
        ),
        {"rid": role_id, "mid": menu_id},
    ).fetchone()
    if exists:
        return

    flags = (1, 1, 1, 1) if full else (0, 1, 0, 0)
    session.execute(
        sa.text(
            """INSERT INTO RoleMenuMap
               (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive)
               VALUES (:rid, :mid, :a, :r, :e, :d, 1)"""
        ),
        {
            "rid": role_id, "mid": menu_id,
            "a": flags[0], "r": flags[1], "e": flags[2], "d": flags[3],
        },
    )
