"""Add Enquiry Status, Quotation Status, Communication Mode, Logs menus and permissions

Revision ID: m1n2o3p4q5r6
Revises: l0m1n2o3p4q5
Create Date: 2026-04-02 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from datetime import datetime


revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, None] = 'l0m1n2o3p4q5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = datetime.utcnow()

# New master menus under "Masters"
NEW_MASTER_MENUS = [
    ("Enquiry Status", "/masters/enq-statuses", "flag"),
    ("Quotation Status", "/masters/quot-statuses", "bookmark"),
    ("Communication Mode", "/masters/communication-modes", "sms"),
]

# New root menu + child
LOGS_MENU = ("Logs", None, "history")
COMM_LOGS_MENU = ("Communication Logs", "/communication-logs", "chat")


def _get_created_by(conn, company_id):
    row = conn.execute(
        sa.text(
            "SELECT TOP 1 u.userId FROM UserMaster u "
            "INNER JOIN UserRoleMap urm ON u.userId = urm.userId "
            "INNER JOIN RoleMaster r ON urm.roleId = r.roleId "
            "WHERE r.companyId = :cid AND r.IsSuperAdmin = 1 AND u.isActive = 1"
        ),
        {"cid": company_id},
    ).first()
    return row[0] if row else 1


def _get_admin_roles(conn, company_id):
    return conn.execute(
        sa.text(
            "SELECT roleId FROM RoleMaster WHERE companyId = :cid AND IsSuperAdmin = 1 AND isActive = 1"
        ),
        {"cid": company_id},
    ).fetchall()


def _insert_menu(conn, company_id, name, url, icon, parent_id, order, created_by):
    """Insert a menu if it doesn't already exist. Return the menuId."""
    existing = conn.execute(
        sa.text(
            "SELECT menuId FROM MenuMaster "
            "WHERE companyId = :cid AND menuName = :name AND isActive = 1"
            + (" AND parentMenuId = :pid" if parent_id else " AND parentMenuId IS NULL")
        ),
        {"cid": company_id, "name": name, "pid": parent_id} if parent_id
        else {"cid": company_id, "name": name},
    ).first()

    if existing:
        return existing[0]

    result = conn.execute(
        sa.text(
            "INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, "
            "isActive, createdon, createdby) "
            "OUTPUT INSERTED.menuId "
            "VALUES (:cid, :name, :url, :icon, :pid, :ord, 1, :now, :cb)"
        ),
        {
            "cid": company_id, "name": name, "url": url, "icon": icon,
            "pid": parent_id, "ord": order, "now": NOW, "cb": created_by,
        },
    )
    return result.scalar()


def _grant_permissions(conn, role_ids, menu_id, created_by):
    """Grant full CRUD to all given roles for a menu."""
    for (role_id,) in role_ids:
        existing = conn.execute(
            sa.text(
                "SELECT roleMenuMapId FROM RoleMenuMap "
                "WHERE roleId = :rid AND menuId = :mid AND isActive = 1"
            ),
            {"rid": role_id, "mid": menu_id},
        ).first()
        if not existing:
            conn.execute(
                sa.text(
                    "INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, "
                    "isActive, createdon, createdby) "
                    "VALUES (:rid, :mid, 1, 1, 1, 1, 1, :now, :cb)"
                ),
                {"rid": role_id, "mid": menu_id, "now": NOW, "cb": created_by},
            )


def upgrade() -> None:
    conn = op.get_bind()
    companies = conn.execute(sa.text("SELECT companyId FROM Company WHERE isActive = 1")).fetchall()

    for (company_id,) in companies:
        created_by = _get_created_by(conn, company_id)
        admin_roles = _get_admin_roles(conn, company_id)

        # --- 1. Add new menus under Masters ---
        masters_row = conn.execute(
            sa.text(
                "SELECT menuId FROM MenuMaster "
                "WHERE companyId = :cid AND menuName = 'Masters' AND parentMenuId IS NULL AND isActive = 1"
            ),
            {"cid": company_id},
        ).first()
        if masters_row:
            masters_menu_id = masters_row[0]
            max_order_row = conn.execute(
                sa.text(
                    "SELECT ISNULL(MAX(menuOrder), 0) FROM MenuMaster "
                    "WHERE companyId = :cid AND parentMenuId = :pid AND isActive = 1"
                ),
                {"cid": company_id, "pid": masters_menu_id},
            ).first()
            next_order = (max_order_row[0] if max_order_row else 0) + 1

            for idx, (name, url, icon) in enumerate(NEW_MASTER_MENUS):
                menu_id = _insert_menu(
                    conn, company_id, name, url, icon,
                    masters_menu_id, next_order + idx, created_by,
                )
                _grant_permissions(conn, admin_roles, menu_id, created_by)

        # --- 2. Add "Logs" root menu ---
        # Find max root menu order
        max_root_row = conn.execute(
            sa.text(
                "SELECT ISNULL(MAX(menuOrder), 0) FROM MenuMaster "
                "WHERE companyId = :cid AND parentMenuId IS NULL AND isActive = 1"
            ),
            {"cid": company_id},
        ).first()
        root_order = (max_root_row[0] if max_root_row else 0) + 1

        logs_name, logs_url, logs_icon = LOGS_MENU
        logs_menu_id = _insert_menu(
            conn, company_id, logs_name, logs_url, logs_icon,
            None, root_order, created_by,
        )
        _grant_permissions(conn, admin_roles, logs_menu_id, created_by)

        # --- 3. Add "Communication Logs" under "Logs" ---
        cl_name, cl_url, cl_icon = COMM_LOGS_MENU
        cl_menu_id = _insert_menu(
            conn, company_id, cl_name, cl_url, cl_icon,
            logs_menu_id, 1, created_by,
        )
        _grant_permissions(conn, admin_roles, cl_menu_id, created_by)


def downgrade() -> None:
    conn = op.get_bind()
    menu_names = (
        "Communication Logs", "Logs",
        "Communication Mode", "Quotation Status", "Enquiry Status",
    )
    for name in menu_names:
        conn.execute(
            sa.text(
                "DELETE FROM RoleMenuMap WHERE menuId IN "
                "(SELECT menuId FROM MenuMaster WHERE menuName = :name)"
            ),
            {"name": name},
        )
        conn.execute(
            sa.text("DELETE FROM MenuMaster WHERE menuName = :name"),
            {"name": name},
        )
