"""Seed the "Commercial HOD" role template per company (idempotent)

The Commercial HOD owns annexure approval. They get:
  * Same hierarchy / location flags as the regular HOD template.
  * CanApproveAnnexure on Quotations  → can approve annexures, AND can
    edit an annexure even after it has been approved (the override path
    in /annexure/{id} PUT honours this same flag).
  * CanRead/CanEdit on Quotations so they can land on the annexure tab,
    open the form and save corrections.
  * CanApprove on Quotations is intentionally OMITTED — that's the
    regular HOD's responsibility for quotation approval. Tweak the
    role afterwards from the role-menu-mapping screen if your org
    wants the same person doing both.

Existing role rows are preserved untouched. Each company gets the
template only if a role of the same name doesn't already exist.

Revision ID: n5o6p7q8r9s0
Revises: m4n5o6p7q8r9
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n5o6p7q8r9s0"
down_revision: Union[str, None] = "m4n5o6p7q8r9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same flag profile as the regular HOD template — hierarchy is what
# matters for visibility, the new privileges live in the menu map.
ROLE_FLAGS = {
    "IsSuperAdmin": 0, "IsCompanyAdmin": 0,
    "numGenMode": "own_code",
    "downwardLevels": -1, "upwardLevels": 0, "includeSubtreeOnUpward": 1,
    "peerAccess": 0, "peerSubtree": 0,
    "locationScopeRequired": 1, "enforceChildLocationSubset": 0,
    "roleLevel": 60, "canApproveTransfers": 0,
}

# Per-menu permission map. Read on the supporting masters so the
# Commercial HOD can navigate the quotation context.
PERMISSIONS = {
    "Customers": {"CanRead": 1},
    "Customer Contacts": {"CanRead": 1},
    "Customer Sites": {"CanRead": 1},
    "Enquiries": {"CanRead": 1, "CanEdit": 1},
    "Quotations": {
        "CanRead": 1, "CanEdit": 1,
        # Annexure-specific approval. Quotation-level CanApprove stays
        # with the regular HOD; flip it here too if your workflow has
        # the same person doing both.
        "CanApproveAnnexure": 1,
    },
    "Communication Logs": {"CanRead": 1, "CanAdd": 1, "CanEdit": 1},
}


def upgrade() -> None:
    bind = op.get_bind()

    companies = bind.execute(
        sa.text("SELECT companyId FROM Company WHERE isActive = 1"),
    ).fetchall()
    menus = bind.execute(
        sa.text("SELECT menuId, menuName FROM MenuMaster WHERE isActive = 1"),
    ).fetchall()
    menu_by_name = {m.menuName: m.menuId for m in menus}

    for co in companies:
        co_id = co.companyId

        existing = bind.execute(
            sa.text(
                "SELECT roleId FROM RoleMaster "
                "WHERE companyId = :co AND roleName = :rn AND isActive = 1"
            ),
            {"co": co_id, "rn": "Commercial HOD"},
        ).fetchone()

        if existing:
            role_id = existing.roleId
        else:
            bind.execute(
                sa.text("""
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
                """),
                {
                    "co": co_id, "rn": "Commercial HOD",
                    "isSA": ROLE_FLAGS["IsSuperAdmin"],
                    "isCA": ROLE_FLAGS["IsCompanyAdmin"],
                    "ngm": ROLE_FLAGS["numGenMode"],
                    "dl": ROLE_FLAGS["downwardLevels"],
                    "ul": ROLE_FLAGS["upwardLevels"],
                    "isu": ROLE_FLAGS["includeSubtreeOnUpward"],
                    "pa": ROLE_FLAGS["peerAccess"],
                    "ps": ROLE_FLAGS["peerSubtree"],
                    "lsr": ROLE_FLAGS["locationScopeRequired"],
                    "ecls": ROLE_FLAGS["enforceChildLocationSubset"],
                    "rl": ROLE_FLAGS["roleLevel"],
                    "cat": ROLE_FLAGS["canApproveTransfers"],
                    "uvl": ROLE_FLAGS["upwardLevels"],
                },
            )
            new_role = bind.execute(
                sa.text(
                    "SELECT roleId FROM RoleMaster "
                    "WHERE companyId = :co AND roleName = :rn AND isActive = 1"
                ),
                {"co": co_id, "rn": "Commercial HOD"},
            ).fetchone()
            role_id = new_role.roleId

        for menu_name, perms in PERMISSIONS.items():
            menu_id = menu_by_name.get(menu_name)
            if menu_id:
                _upsert_role_menu_map(bind, role_id, menu_id, perms)


def _upsert_role_menu_map(bind, role_id: int, menu_id: int, perms: dict) -> None:
    """Create or update a RoleMenuMap row. Includes the new
    ``CanApproveAnnexure`` column added in m4n5o6p7q8r9 — fields
    not in ``perms`` default to 0 so a fresh row gets a deterministic
    zero baseline rather than DB-server-defaults that may differ."""
    existing = bind.execute(
        sa.text(
            "SELECT roleMenuMapId FROM RoleMenuMap "
            "WHERE roleId = :rid AND menuId = :mid"
        ),
        {"rid": role_id, "mid": menu_id},
    ).fetchone()

    all_flags = {
        "CanAdd": 0, "CanRead": 0, "CanEdit": 0, "CanDelete": 0,
        "CanEditNumber": 0, "CanApprove": 0, "CanRevise": 0,
        "CanTransferOwnership": 0, "CanGenerateUnderOthers": 0,
        "CanApproveAnnexure": 0,
    }
    all_flags.update({k: (1 if v else 0) for k, v in perms.items()})

    if existing:
        bind.execute(
            sa.text("""
                UPDATE RoleMenuMap SET
                    CanAdd = :ca, CanRead = :cr, CanEdit = :ce, CanDelete = :cd,
                    CanEditNumber = :cen, CanApprove = :capp, CanRevise = :crev,
                    CanTransferOwnership = :cto, CanGenerateUnderOthers = :cgo,
                    CanApproveAnnexure = :caa,
                    isActive = 1
                WHERE roleMenuMapId = :id
            """),
            {
                **{
                    "ca": all_flags["CanAdd"], "cr": all_flags["CanRead"],
                    "ce": all_flags["CanEdit"], "cd": all_flags["CanDelete"],
                    "cen": all_flags["CanEditNumber"], "capp": all_flags["CanApprove"],
                    "crev": all_flags["CanRevise"], "cto": all_flags["CanTransferOwnership"],
                    "cgo": all_flags["CanGenerateUnderOthers"],
                    "caa": all_flags["CanApproveAnnexure"],
                    "id": existing.roleMenuMapId,
                },
            },
        )
    else:
        bind.execute(
            sa.text("""
                INSERT INTO RoleMenuMap
                    (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete,
                     CanEditNumber, CanApprove, CanRevise,
                     CanTransferOwnership, CanGenerateUnderOthers,
                     CanApproveAnnexure, isActive)
                VALUES (:rid, :mid, :ca, :cr, :ce, :cd, :cen, :capp, :crev,
                        :cto, :cgo, :caa, 1)
            """),
            {
                "rid": role_id, "mid": menu_id,
                "ca": all_flags["CanAdd"], "cr": all_flags["CanRead"],
                "ce": all_flags["CanEdit"], "cd": all_flags["CanDelete"],
                "cen": all_flags["CanEditNumber"], "capp": all_flags["CanApprove"],
                "crev": all_flags["CanRevise"], "cto": all_flags["CanTransferOwnership"],
                "cgo": all_flags["CanGenerateUnderOthers"],
                "caa": all_flags["CanApproveAnnexure"],
            },
        )


def downgrade() -> None:
    # Soft-delete the Commercial HOD rows. Don't hard-delete because
    # admins may have already mapped users to the role; preserving the
    # ID lets a re-upgrade restore the same row instead of creating a
    # duplicate with a new ID.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE RoleMaster SET isActive = 0 WHERE roleName = 'Commercial HOD'"
        )
    )
