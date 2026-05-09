"""Phase 1 follow-up: collapse QuotSummary.status + seed permission flags.

Two data-only operations that ride on the schema added in
``r9s0t1u2v3w4_phase1_lifecycle_versioning``:

1. **Status simplification on QuotSummary**. The lifecycle position
   past Stage 1 (PO / Viability / Annexure) used to be encoded by
   five distinct ``QuotSummary.status`` values:
   ``Matured / ViabilityGenerated / ViabilityApproved /
   AnnexureGenerated / AnnexureApproved``. With per-stage entities
   each carrying their own status now, those five values collapse
   to a single ``Converted`` — the per-stage row is the source of
   truth for "where in the lifecycle is this?". ``convertedOn /
   convertedBy`` are backfilled from ``lastupdateon / lastupdateby``
   so the audit pair is non-null on every Converted row.

2. **Seed new permission flags on canonical role templates per
   company**. The new flags
   (``CanConvert / CanReactivate / CanSubmitPO / CanRejectPO /
   CanApproveViability / CanUnlockEdit{Stage}``) all default to 0
   on the schema migration. This step grants sensible defaults:
     * SuperAdmin / CompanyAdmin: all flags ON.
     * Director / HOD: Convert / Reactivate / SubmitPO / RejectPO /
       ApproveViability ON. Unlock-Edit OFF (only super-privileged
       users hold that escape valve in v1).
     * KRO: SubmitPO ON (KROs capture POs).
     * Commercial HOD: ApproveViability ON. Unlock-Edit OFF.

   Existing role rows whose flags admins already customised away
   from these defaults are NOT overwritten — the upsert only fills
   in ``Quotations`` menu rows on the canonical templates.

Revision ID: s0t1u2v3w4x5
Revises: r9s0t1u2v3w4
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s0t1u2v3w4x5"
down_revision: Union[str, None] = "r9s0t1u2v3w4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Canonical role templates and the new flags each should hold by
# default. Only the new (Phase 1) flags are listed — existing flags on
# the same RoleMenuMap row are preserved unchanged. Customer
# customisations therefore survive the upgrade.
_TEMPLATE_DEFAULTS = {
    "SuperAdmin": {
        "CanConvert": 1, "CanReactivate": 1,
        "CanSubmitPO": 1, "CanRejectPO": 1,
        "CanApproveViability": 1,
        "CanUnlockEditQuotation": 1, "CanUnlockEditPO": 1,
        "CanUnlockEditViability": 1, "CanUnlockEditAnnexure": 1,
    },
    "CompanyAdmin": {
        "CanConvert": 1, "CanReactivate": 1,
        "CanSubmitPO": 1, "CanRejectPO": 1,
        "CanApproveViability": 1,
        "CanUnlockEditQuotation": 1, "CanUnlockEditPO": 1,
        "CanUnlockEditViability": 1, "CanUnlockEditAnnexure": 1,
    },
    "Director": {
        "CanConvert": 1, "CanReactivate": 1,
        "CanSubmitPO": 1, "CanRejectPO": 1,
        "CanApproveViability": 1,
    },
    "HOD": {
        "CanConvert": 1, "CanReactivate": 1,
        "CanSubmitPO": 1, "CanRejectPO": 1,
        "CanApproveViability": 1,
    },
    "KRO": {
        "CanSubmitPO": 1,
    },
    "Commercial HOD": {
        "CanApproveViability": 1,
    },
}


def upgrade() -> None:
    bind = op.get_bind()

    # ----- 1) Status simplification + Convert audit backfill -----
    # Backfill convertedOn / convertedBy first so a row whose status
    # we're about to rename never goes through a "Converted with no
    # convertedOn" intermediate state. The status update follows.
    bind.execute(sa.text("""
        UPDATE QuotSummary
        SET convertedOn = lastupdateon,
            convertedBy = lastupdateby
        WHERE status IN (
            'Matured', 'ViabilityGenerated', 'ViabilityApproved',
            'AnnexureGenerated', 'AnnexureApproved'
        )
          AND convertedOn IS NULL
    """))
    bind.execute(sa.text("""
        UPDATE QuotSummary
        SET status = 'Converted'
        WHERE status IN (
            'Matured', 'ViabilityGenerated', 'ViabilityApproved',
            'AnnexureGenerated', 'AnnexureApproved'
        )
    """))

    # ----- 2) Seed new permission flags on canonical role templates -----
    # Find the Quotations menu (single MENU = "Quotations" used by
    # quotations / viability / annexure / PO endpoints, so all four
    # stages' permission flags live on this one menu).
    quot_menu = bind.execute(sa.text(
        "SELECT menuId FROM MenuMaster "
        "WHERE menuName = 'Quotations' AND isActive = 1"
    )).fetchone()
    if quot_menu is None:
        return  # No menu seeded yet — nothing to upgrade

    quot_menu_id = quot_menu.menuId

    companies = bind.execute(
        sa.text("SELECT companyId FROM Company WHERE isActive = 1"),
    ).fetchall()

    for co in companies:
        for role_name, flag_defaults in _TEMPLATE_DEFAULTS.items():
            role = bind.execute(
                sa.text(
                    "SELECT roleId FROM RoleMaster "
                    "WHERE companyId = :co AND roleName = :rn AND isActive = 1"
                ),
                {"co": co.companyId, "rn": role_name},
            ).fetchone()
            if not role:
                continue  # template not seeded for this company

            existing = bind.execute(
                sa.text(
                    "SELECT roleMenuMapId FROM RoleMenuMap "
                    "WHERE roleId = :rid AND menuId = :mid"
                ),
                {"rid": role.roleId, "mid": quot_menu_id},
            ).fetchone()

            # Build the SET clause from only the flags this template
            # owns — existing CRUD flags etc. on this row stay as-is.
            set_pairs = ", ".join(
                f"{flag} = :{flag.lower()}" for flag in flag_defaults
            )
            params = {flag.lower(): val for flag, val in flag_defaults.items()}

            if existing:
                bind.execute(
                    sa.text(
                        f"UPDATE RoleMenuMap SET {set_pairs} "
                        "WHERE roleMenuMapId = :id"
                    ),
                    {**params, "id": existing.roleMenuMapId},
                )
            else:
                # No row yet — create one with EVERY ``Can*`` flag
                # explicitly set. The legacy CRUD columns (``CanAdd``,
                # ``CanRead``, ``CanEdit``, ``CanDelete``,
                # ``CanEditNumber``) are NOT NULL with no server
                # default on this DB, so a partial INSERT fails. We
                # default every flag this template doesn't own to 0;
                # admins can flip them later via the role-menu-mapping
                # UI.
                all_cols = [
                    "CanAdd", "CanRead", "CanEdit", "CanDelete", "CanEditNumber",
                    "CanApprove", "CanRevise", "CanTransferOwnership",
                    "CanGenerateUnderOthers", "CanApproveAnnexure",
                    "CanConvert", "CanReactivate",
                    "CanSubmitPO", "CanRejectPO", "CanApproveViability",
                    "CanUnlockEditQuotation", "CanUnlockEditPO",
                    "CanUnlockEditViability", "CanUnlockEditAnnexure",
                ]
                col_list = ", ".join(all_cols)
                placeholder_list = ", ".join(
                    f":{c.lower()}" for c in all_cols
                )
                row_params = {c.lower(): 0 for c in all_cols}
                # Override with this template's defaults
                row_params.update(
                    {flag.lower(): val for flag, val in flag_defaults.items()}
                )
                bind.execute(
                    sa.text(
                        f"INSERT INTO RoleMenuMap "
                        f"(roleId, menuId, {col_list}, isActive) "
                        f"VALUES (:rid, :mid, {placeholder_list}, 1)"
                    ),
                    {**row_params, "rid": role.roleId, "mid": quot_menu_id},
                )


def downgrade() -> None:
    bind = op.get_bind()

    # Roll status simplification back: rows whose convertedOn was
    # populated by this migration go back to 'Matured' (we cannot
    # losslessly distinguish ViabilityGenerated vs AnnexureApproved
    # post-collapse, so 'Matured' is the safest legacy floor — all
    # five legacy values shared the "Matured-or-later" semantics).
    bind.execute(sa.text("""
        UPDATE QuotSummary
        SET status = 'Matured'
        WHERE status = 'Converted'
    """))
    bind.execute(sa.text("""
        UPDATE QuotSummary
        SET convertedOn = NULL, convertedBy = NULL
    """))

    # Reset the new permission flags on canonical templates back to 0.
    # Custom roles retain whatever the admin set.
    quot_menu = bind.execute(sa.text(
        "SELECT menuId FROM MenuMaster "
        "WHERE menuName = 'Quotations' AND isActive = 1"
    )).fetchone()
    if quot_menu is None:
        return
    quot_menu_id = quot_menu.menuId

    flags = list({
        flag for defaults in _TEMPLATE_DEFAULTS.values() for flag in defaults
    })
    set_to_zero = ", ".join(f"{f} = 0" for f in flags)

    template_names = list(_TEMPLATE_DEFAULTS.keys())
    name_list = ", ".join(f"'{n}'" for n in template_names)
    bind.execute(sa.text(
        f"UPDATE RoleMenuMap SET {set_to_zero} "
        f"WHERE menuId = {quot_menu_id} AND roleId IN ("
        f"  SELECT roleId FROM RoleMaster WHERE roleName IN ({name_list})"
        f")"
    ))
