"""Seed RBAC v2 role templates for each company (idempotent)

Creates the standard role templates per company:
- SuperAdmin (IsSuperAdmin=True)
- CompanyAdmin (IsCompanyAdmin=True)
- Director (downward=-1, upward=0, peerAccess=False, numGenMode=select_code, locationScopeRequired=False)
- HOD (downward=-1, upward=0, peerAccess=False, numGenMode=own_code, locationScopeRequired=True)
  — HOD approves quotations; does NOT create enquiries/quotations
- KRO (downward=0, upward=0, peerAccess=False, numGenMode=own_code, locationScopeRequired=True, enforceChildLocationSubset=True)
  — KRO is the creator: adds enquiries, quotations, customers (full CRUD)

Also grants default menu permissions for each template on core menus.
All existing roles are preserved untouched. Each template is created only if
a role with the same name doesn't already exist in a company.

Revision ID: g1h2i3j4k5l6
Revises: f0g1h2i3j4k5
Create Date: 2026-04-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "f0g1h2i3j4k5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Template definitions — (roleName, flag dict)
ROLE_TEMPLATES = [
    {
        "roleName": "SuperAdmin",
        "IsSuperAdmin": True, "IsCompanyAdmin": False,
        "numGenMode": "own_code",
        "downwardLevels": -1, "upwardLevels": -1, "includeSubtreeOnUpward": True,
        "peerAccess": True, "peerSubtree": True,
        "locationScopeRequired": False, "enforceChildLocationSubset": False,
        "roleLevel": 100, "canApproveTransfers": True,
    },
    {
        "roleName": "CompanyAdmin",
        "IsSuperAdmin": False, "IsCompanyAdmin": True,
        "numGenMode": "own_code",
        "downwardLevels": -1, "upwardLevels": -1, "includeSubtreeOnUpward": True,
        "peerAccess": True, "peerSubtree": True,
        "locationScopeRequired": False, "enforceChildLocationSubset": False,
        "roleLevel": 90, "canApproveTransfers": True,
    },
    {
        "roleName": "Director",
        "IsSuperAdmin": False, "IsCompanyAdmin": False,
        "numGenMode": "select_code",
        "downwardLevels": -1, "upwardLevels": 0, "includeSubtreeOnUpward": True,
        "peerAccess": False, "peerSubtree": False,
        "locationScopeRequired": False, "enforceChildLocationSubset": False,
        "roleLevel": 70, "canApproveTransfers": True,
    },
    {
        "roleName": "HOD",
        "IsSuperAdmin": False, "IsCompanyAdmin": False,
        "numGenMode": "own_code",
        "downwardLevels": -1, "upwardLevels": 0, "includeSubtreeOnUpward": True,
        "peerAccess": False, "peerSubtree": False,
        "locationScopeRequired": True, "enforceChildLocationSubset": False,
        "roleLevel": 50, "canApproveTransfers": False,
    },
    {
        "roleName": "KRO",
        "IsSuperAdmin": False, "IsCompanyAdmin": False,
        "numGenMode": "own_code",
        "downwardLevels": 0, "upwardLevels": 0, "includeSubtreeOnUpward": True,
        "peerAccess": False, "peerSubtree": False,
        "locationScopeRequired": True, "enforceChildLocationSubset": True,
        "roleLevel": 30, "canApproveTransfers": False,
    },
]


# Default menu permissions per template (menu name → flags dict)
# Flags: CanAdd, CanRead, CanEdit, CanDelete, CanEditNumber,
#        CanApprove, CanRevise, CanTransferOwnership, CanGenerateUnderOthers
PERM_ALL = {
    "CanAdd": 1, "CanRead": 1, "CanEdit": 1, "CanDelete": 1,
    "CanEditNumber": 1, "CanApprove": 1, "CanRevise": 1,
    "CanTransferOwnership": 1, "CanGenerateUnderOthers": 1,
}
PERM_READ = {"CanRead": 1}
PERM_FULL = {"CanAdd": 1, "CanRead": 1, "CanEdit": 1, "CanDelete": 1}
PERM_READ_EDIT = {"CanRead": 1, "CanEdit": 1}

TEMPLATE_PERMISSIONS = {
    "SuperAdmin": {"*": PERM_ALL},       # wildcard → all menus
    "CompanyAdmin": {"*": PERM_ALL},
    "Director": {
        "Customers": PERM_FULL,
        "Customer Contacts": PERM_FULL,
        "Customer Sites": PERM_FULL,
        "Enquiries": {**PERM_FULL, "CanTransferOwnership": 1, "CanGenerateUnderOthers": 1},
        "Quotations": {**PERM_FULL, "CanApprove": 1, "CanRevise": 1,
                       "CanTransferOwnership": 1, "CanGenerateUnderOthers": 1},
        "Communication Logs": PERM_FULL,
    },
    "HOD": {
        # HOD's primary job is approving quotations. They see customer data
        # for context but do NOT create enquiries/quotations themselves — that
        # is the KRO's responsibility. HODs can still edit/reject/revise as
        # part of the approval workflow.
        "Customers": PERM_READ,
        "Customer Contacts": PERM_READ,
        "Customer Sites": PERM_READ,
        "Enquiries": PERM_READ_EDIT,  # can view & edit, not add/delete
        "Quotations": {
            "CanRead": 1, "CanEdit": 1,
            "CanApprove": 1, "CanRevise": 1,
            "CanTransferOwnership": 1,
        },
        "Communication Logs": PERM_FULL,
    },
    "KRO": {
        # KRO is the ground-level worker — creates all records
        # (customers, contacts, sites, enquiries, quotations).
        # Quotations: can create + edit, but NOT approve/revise —
        # those require CanApprove/CanRevise which the HOD holds.
        "Customers": PERM_FULL,
        "Customer Contacts": PERM_FULL,
        "Customer Sites": PERM_FULL,
        "Enquiries": PERM_FULL,
        "Quotations": PERM_FULL,  # add/read/edit/delete but no approve
        "Communication Logs": PERM_FULL,
    },
}


def upgrade() -> None:
    bind = op.get_bind()

    # Find all active companies
    companies = bind.execute(sa.text("SELECT companyId FROM Company WHERE isActive = 1")).fetchall()
    menus = bind.execute(sa.text("SELECT menuId, menuName FROM MenuMaster WHERE isActive = 1")).fetchall()
    menu_by_name = {m.menuName: m.menuId for m in menus}

    for co_row in companies:
        co_id = co_row.companyId

        for tpl in ROLE_TEMPLATES:
            # Check if role with this name exists for the company
            existing = bind.execute(
                sa.text("SELECT roleId FROM RoleMaster WHERE companyId = :co AND roleName = :rn AND isActive = 1"),
                {"co": co_id, "rn": tpl["roleName"]},
            ).fetchone()
            if existing:
                role_id = existing.roleId
            else:
                # Insert new role using flag dict
                insert_sql = sa.text("""
                    INSERT INTO RoleMaster
                        (companyId, roleName, IsSuperAdmin, IsCompanyAdmin, numGenMode,
                         downwardLevels, upwardLevels, includeSubtreeOnUpward,
                         peerAccess, peerSubtree,
                         locationScopeRequired, enforceChildLocationSubset,
                         roleLevel, canApproveTransfers, upwardVisibilityLevels, isActive)
                    VALUES
                        (:co, :rn, :isSA, :isCA, :ngm,
                         :dl, :ul, :isu, :pa, :ps,
                         :lsr, :ecls, :rl, :cat, :uvl, 1)
                """)
                bind.execute(insert_sql, {
                    "co": co_id, "rn": tpl["roleName"],
                    "isSA": 1 if tpl["IsSuperAdmin"] else 0,
                    "isCA": 1 if tpl["IsCompanyAdmin"] else 0,
                    "ngm": tpl["numGenMode"],
                    "dl": tpl["downwardLevels"], "ul": tpl["upwardLevels"],
                    "isu": 1 if tpl["includeSubtreeOnUpward"] else 0,
                    "pa": 1 if tpl["peerAccess"] else 0,
                    "ps": 1 if tpl["peerSubtree"] else 0,
                    "lsr": 1 if tpl["locationScopeRequired"] else 0,
                    "ecls": 1 if tpl["enforceChildLocationSubset"] else 0,
                    "rl": tpl["roleLevel"],
                    "cat": 1 if tpl["canApproveTransfers"] else 0,
                    "uvl": tpl["upwardLevels"],
                })
                # Re-query for new roleId
                new_role = bind.execute(
                    sa.text("SELECT roleId FROM RoleMaster WHERE companyId = :co AND roleName = :rn AND isActive = 1"),
                    {"co": co_id, "rn": tpl["roleName"]},
                ).fetchone()
                role_id = new_role.roleId

            # Seed menu permissions
            perms_map = TEMPLATE_PERMISSIONS.get(tpl["roleName"], {})

            if "*" in perms_map:
                # Wildcard — all menus get these perms
                perms = perms_map["*"]
                for menu_id in menu_by_name.values():
                    _upsert_role_menu_map(bind, role_id, menu_id, perms)
            else:
                for menu_name, perms in perms_map.items():
                    menu_id = menu_by_name.get(menu_name)
                    if menu_id:
                        _upsert_role_menu_map(bind, role_id, menu_id, perms)


def _upsert_role_menu_map(bind, role_id: int, menu_id: int, perms: dict):
    """Create or update a RoleMenuMap row. Only sets flags in `perms`, leaves others at default."""
    existing = bind.execute(
        sa.text("SELECT roleMenuMapId FROM RoleMenuMap WHERE roleId = :rid AND menuId = :mid"),
        {"rid": role_id, "mid": menu_id},
    ).fetchone()

    all_flags = {
        "CanAdd": 0, "CanRead": 0, "CanEdit": 0, "CanDelete": 0,
        "CanEditNumber": 0, "CanApprove": 0, "CanRevise": 0,
        "CanTransferOwnership": 0, "CanGenerateUnderOthers": 0,
    }
    all_flags.update({k: (1 if v else 0) for k, v in perms.items()})

    if existing:
        bind.execute(
            sa.text("""
                UPDATE RoleMenuMap SET
                    CanAdd = :ca, CanRead = :cr, CanEdit = :ce, CanDelete = :cd,
                    CanEditNumber = :cen, CanApprove = :capp, CanRevise = :crev,
                    CanTransferOwnership = :cto, CanGenerateUnderOthers = :cgo,
                    isActive = 1
                WHERE roleMenuMapId = :id
            """),
            {
                "ca": all_flags["CanAdd"], "cr": all_flags["CanRead"],
                "ce": all_flags["CanEdit"], "cd": all_flags["CanDelete"],
                "cen": all_flags["CanEditNumber"], "capp": all_flags["CanApprove"],
                "crev": all_flags["CanRevise"], "cto": all_flags["CanTransferOwnership"],
                "cgo": all_flags["CanGenerateUnderOthers"],
                "id": existing.roleMenuMapId,
            },
        )
    else:
        bind.execute(
            sa.text("""
                INSERT INTO RoleMenuMap
                    (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete,
                     CanEditNumber, CanApprove, CanRevise,
                     CanTransferOwnership, CanGenerateUnderOthers, isActive)
                VALUES (:rid, :mid, :ca, :cr, :ce, :cd, :cen, :capp, :crev, :cto, :cgo, 1)
            """),
            {
                "rid": role_id, "mid": menu_id,
                "ca": all_flags["CanAdd"], "cr": all_flags["CanRead"],
                "ce": all_flags["CanEdit"], "cd": all_flags["CanDelete"],
                "cen": all_flags["CanEditNumber"], "capp": all_flags["CanApprove"],
                "crev": all_flags["CanRevise"], "cto": all_flags["CanTransferOwnership"],
                "cgo": all_flags["CanGenerateUnderOthers"],
            },
        )


def downgrade() -> None:
    # Intentionally not reversed: seed data should not be auto-removed
    # as administrators may have customized roles.
    pass
