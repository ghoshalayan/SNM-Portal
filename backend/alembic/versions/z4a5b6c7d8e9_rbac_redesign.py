"""RBAC redesign: role properties, record ownership, ownership transfers

Revision ID: z4a5b6c7d8e9
Revises: y3z4a5b6c7d8
Create Date: 2026-04-11

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "z4a5b6c7d8e9"
down_revision: Union[str, None] = "y3z4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Role properties ---
    op.add_column("RoleMaster", sa.Column("roleLevel", sa.Integer, server_default="0", nullable=False))
    op.add_column("RoleMaster", sa.Column("locationScopeRequired", sa.Boolean, server_default=sa.text("1"), nullable=False))
    op.add_column("RoleMaster", sa.Column("canApproveTransfers", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RoleMaster", sa.Column("upwardVisibilityLevels", sa.Integer, server_default="0", nullable=False))

    # SuperAdmin/Admin roles get high level + approve + no location scope
    op.execute("""
        UPDATE RoleMaster SET roleLevel = 100, locationScopeRequired = 0, canApproveTransfers = 1
        WHERE IsSuperAdmin = 1
    """)

    # --- 2. Owner columns on Enquiry ---
    op.add_column("CustomerEnquiry", sa.Column("ownerUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True))
    op.add_column("CustomerEnquiry", sa.Column("ownerRoleId", sa.Integer, sa.ForeignKey("RoleMaster.roleId"), nullable=True))
    # Backfill: set owner = createdby for existing records
    op.execute("UPDATE CustomerEnquiry SET ownerUserId = createdby WHERE ownerUserId IS NULL AND createdby IS NOT NULL")

    # --- 3. Owner columns on Quotation ---
    op.add_column("QuotSummary", sa.Column("ownerUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True))
    op.add_column("QuotSummary", sa.Column("ownerRoleId", sa.Integer, sa.ForeignKey("RoleMaster.roleId"), nullable=True))
    # Backfill: set owner = createdby for existing records
    op.execute("UPDATE QuotSummary SET ownerUserId = createdby WHERE ownerUserId IS NULL AND createdby IS NOT NULL")

    # --- 4. OwnershipTransfer table ---
    op.create_table(
        "OwnershipTransfer",
        sa.Column("transferId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("entityType", sa.String(20), nullable=False),
        sa.Column("entityId", sa.Integer, nullable=False),
        sa.Column("fromUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=False),
        sa.Column("toUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=False),
        sa.Column("requestedBy", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=False),
        sa.Column("requestedOn", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("approvedBy", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("approvedOn", sa.DateTime, nullable=True),
        sa.Column("remarks", sa.String(500), nullable=True),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
        sa.Column("isActive", sa.Boolean, server_default=sa.text("1"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("OwnershipTransfer")
    op.drop_column("QuotSummary", "ownerRoleId")
    op.drop_column("QuotSummary", "ownerUserId")
    op.drop_column("CustomerEnquiry", "ownerRoleId")
    op.drop_column("CustomerEnquiry", "ownerUserId")
    op.drop_column("RoleMaster", "upwardVisibilityLevels")
    op.drop_column("RoleMaster", "canApproveTransfers")
    op.drop_column("RoleMaster", "locationScopeRequired")
    op.drop_column("RoleMaster", "roleLevel")
