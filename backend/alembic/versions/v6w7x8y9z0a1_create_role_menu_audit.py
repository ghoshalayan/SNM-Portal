"""Create RoleMenuMapAudit

Per-flag change log for the role-menu-mapping editor. One row per
(roleId, menuId, field) change, capturing the old and new boolean plus
who/when. Feeds the audit history panel on the new role permissions UI.

Rows are additive only — we never prune, so this also acts as a simple
forensic trail for "who granted delete access to Customers".

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "v6w7x8y9z0a1"
down_revision: Union[str, None] = "u5v6w7x8y9z0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "RoleMenuMapAudit",
        sa.Column("auditId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("roleId", sa.Integer, sa.ForeignKey("RoleMaster.roleId"), nullable=False),
        sa.Column("menuId", sa.Integer, sa.ForeignKey("MenuMaster.menuId"), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("oldValue", sa.Boolean, nullable=True),
        sa.Column("newValue", sa.Boolean, nullable=True),
        sa.Column("changedby", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("changedon", sa.DateTime, nullable=False),
    )
    op.create_index(
        "IX_RoleMenuMapAudit_roleId_changedon",
        "RoleMenuMapAudit",
        ["roleId", "changedon"],
    )


def downgrade() -> None:
    op.drop_index("IX_RoleMenuMapAudit_roleId_changedon", table_name="RoleMenuMapAudit")
    op.drop_table("RoleMenuMapAudit")
