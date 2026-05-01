"""Rename BDM role to HOD

Business model change: "BDM" (Business Development Manager) role is renamed to
"HOD" (Head of Department) across all companies. The HOD's responsibility is
also clarified — HODs primarily *approve* quotations; they do NOT create enquiries
or quotations (that is the KRO's job).

Strategy (safe for production):
1. For every active role named "BDM" in any company:
   - If a role named "HOD" already exists in that company (fresh install via
     re-running the seeder): merge — move all UserRoleMap rows from BDM to HOD,
     then deactivate the BDM role. RoleMenuMap for the old BDM becomes orphaned
     (harmless; isActive stays True but roleId no longer has active users).
   - Otherwise: rename the role in place (roleName = 'HOD'). All UserRoleMap /
     RoleMenuMap rows stay intact because they reference roleId, not name.

2. Existing per-role flags (downwardLevels, locationScopeRequired, etc.) are
   preserved — sites already using BDM with customized flags don't get reset.

This migration is idempotent: running twice is a no-op on the second run.

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-04-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "o9p0q1r2s3t4"
down_revision: Union[str, None] = "n8o9p0q1r2s3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Find all active BDM roles across companies
    bdm_rows = bind.execute(sa.text("""
        SELECT roleId, companyId FROM RoleMaster
        WHERE roleName = 'BDM' AND isActive = 1
    """)).fetchall()

    for bdm_role_id, company_id in bdm_rows:
        # Check if an HOD role already exists for this company
        existing_hod = bind.execute(sa.text("""
            SELECT roleId FROM RoleMaster
            WHERE companyId = :cid AND roleName = 'HOD' AND isActive = 1
        """), {"cid": company_id}).fetchone()

        if existing_hod:
            new_role_id = existing_hod.roleId
            # Move all UserRoleMap entries from BDM → HOD
            bind.execute(sa.text("""
                UPDATE UserRoleMap
                SET roleId = :new_id, lastupdateon = SYSUTCDATETIME()
                WHERE roleId = :old_id AND isActive = 1
            """), {"new_id": new_role_id, "old_id": bdm_role_id})

            # Deactivate the old BDM role (RoleMenuMap rows become inert)
            bind.execute(sa.text("""
                UPDATE RoleMaster
                SET isActive = 0, lastupdateon = SYSUTCDATETIME()
                WHERE roleId = :old_id
            """), {"old_id": bdm_role_id})
        else:
            # Simple rename in place — preserves roleId so all FKs stay valid
            bind.execute(sa.text("""
                UPDATE RoleMaster
                SET roleName = 'HOD', lastupdateon = SYSUTCDATETIME()
                WHERE roleId = :rid
            """), {"rid": bdm_role_id})


def downgrade() -> None:
    # Reverse the rename (only works when no fresh HOD roles exist from seeder).
    # Merging cannot be cleanly reversed, so this is best-effort.
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE RoleMaster
        SET roleName = 'BDM', lastupdateon = SYSUTCDATETIME()
        WHERE roleName = 'HOD' AND isActive = 1
    """))
