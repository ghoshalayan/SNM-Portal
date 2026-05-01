"""RBAC v2 — schema changes

Adds:
- RoleMaster: IsCompanyAdmin, downwardLevels, upwardLevels, includeSubtreeOnUpward,
  peerSubtree, enforceChildLocationSubset
- RoleMenuMap: CanApprove, CanRevise, CanTransferOwnership, CanGenerateUnderOthers
- CustomerMaster: ownerUserId, ownerRoleId
- CommunicationLog: ownerUserId, ownerRoleId

Backfill:
- upwardLevels <- upwardVisibilityLevels (preserve existing behavior)
- CustomerMaster.ownerUserId <- createdby (fallback: first SuperAdmin in company)
- CommunicationLog.ownerUserId <- createdby (fallback: first SuperAdmin in company)

Revision ID: f0g1h2i3j4k5
Revises: e9f0g1h2i3j4
Create Date: 2026-04-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f0g1h2i3j4k5"
down_revision: Union[str, None] = "e9f0g1h2i3j4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===== Role: add new flags =====
    op.add_column("RoleMaster", sa.Column("IsCompanyAdmin", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMaster", sa.Column("downwardLevels", sa.Integer, server_default=sa.text("-1"), nullable=False))
    op.add_column("RoleMaster", sa.Column("upwardLevels", sa.Integer, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMaster", sa.Column("includeSubtreeOnUpward", sa.Boolean, server_default=sa.text("1"), nullable=False))
    op.add_column("RoleMaster", sa.Column("peerSubtree", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMaster", sa.Column("enforceChildLocationSubset", sa.Boolean, server_default=sa.text("0"), nullable=False))

    # Preserve existing upward behavior: copy from legacy column
    op.execute("UPDATE RoleMaster SET upwardLevels = upwardVisibilityLevels")

    # ===== RoleMenuMap: add new permission flags =====
    op.add_column("RoleMenuMap", sa.Column("CanApprove", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMenuMap", sa.Column("CanRevise", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMenuMap", sa.Column("CanTransferOwnership", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMenuMap", sa.Column("CanGenerateUnderOthers", sa.Boolean, server_default=sa.text("0"), nullable=False))

    # ===== CustomerMaster: owner tracking =====
    op.add_column("CustomerMaster", sa.Column("ownerUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True))
    op.add_column("CustomerMaster", sa.Column("ownerRoleId", sa.Integer, sa.ForeignKey("RoleMaster.roleId"), nullable=True))

    # Backfill Customer ownerUserId: prefer createdby, else first SuperAdmin in same company
    op.execute("""
        UPDATE CustomerMaster
        SET ownerUserId = createdby
        WHERE createdby IS NOT NULL
    """)
    op.execute("""
        UPDATE CustomerMaster
        SET ownerUserId = (
            SELECT TOP 1 u.userId
            FROM UserMaster u
            INNER JOIN UserRoleMap urm ON urm.userId = u.userId AND urm.companyId = CustomerMaster.companyId
            INNER JOIN RoleMaster r ON r.roleId = urm.roleId
            WHERE u.companyId = CustomerMaster.companyId
              AND r.IsSuperAdmin = 1
              AND u.isActive = 1
        )
        WHERE ownerUserId IS NULL
    """)

    # ===== CommunicationLog: owner tracking =====
    op.add_column("CommunicationLog", sa.Column("ownerUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True))
    op.add_column("CommunicationLog", sa.Column("ownerRoleId", sa.Integer, sa.ForeignKey("RoleMaster.roleId"), nullable=True))

    # Backfill CommunicationLog ownerUserId
    op.execute("""
        UPDATE CommunicationLog
        SET ownerUserId = createdby
        WHERE createdby IS NOT NULL
    """)
    op.execute("""
        UPDATE CommunicationLog
        SET ownerUserId = (
            SELECT TOP 1 u.userId
            FROM UserMaster u
            INNER JOIN UserRoleMap urm ON urm.userId = u.userId AND urm.companyId = CommunicationLog.companyId
            INNER JOIN RoleMaster r ON r.roleId = urm.roleId
            WHERE u.companyId = CommunicationLog.companyId
              AND r.IsSuperAdmin = 1
              AND u.isActive = 1
        )
        WHERE ownerUserId IS NULL
    """)


def downgrade() -> None:
    # Communication Log
    op.drop_column("CommunicationLog", "ownerRoleId")
    op.drop_column("CommunicationLog", "ownerUserId")

    # Customer Master
    op.drop_column("CustomerMaster", "ownerRoleId")
    op.drop_column("CustomerMaster", "ownerUserId")

    # Role Menu Map
    op.drop_column("RoleMenuMap", "CanGenerateUnderOthers")
    op.drop_column("RoleMenuMap", "CanTransferOwnership")
    op.drop_column("RoleMenuMap", "CanRevise")
    op.drop_column("RoleMenuMap", "CanApprove")

    # Role Master
    op.drop_column("RoleMaster", "enforceChildLocationSubset")
    op.drop_column("RoleMaster", "peerSubtree")
    op.drop_column("RoleMaster", "includeSubtreeOnUpward")
    op.drop_column("RoleMaster", "upwardLevels")
    op.drop_column("RoleMaster", "downwardLevels")
    op.drop_column("RoleMaster", "IsCompanyAdmin")
