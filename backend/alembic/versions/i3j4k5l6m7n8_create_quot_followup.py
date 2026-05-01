"""Create QuotFollowUp table

Mirrors CustomerEnqFollowUp structure for Quotations.

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-04-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i3j4k5l6m7n8"
down_revision: Union[str, None] = "h2i3j4k5l6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "QuotFollowUp",
        sa.Column("quotfollowupid", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("quotId", sa.Integer, sa.ForeignKey("QuotSummary.quotId"), nullable=False),
        sa.Column("followupdate", sa.Date, nullable=True),
        sa.Column("followupremarks", sa.String(500), nullable=True),
        sa.Column("followupmode", sa.String(50), nullable=True),
        sa.Column("nextfollowupdate", sa.Date, nullable=True),
        # AuditMixin columns
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
        sa.Column("isActive", sa.Boolean, server_default=sa.text("1"), nullable=False),
    )
    op.create_index(
        "ix_quotfollowup_quotid",
        "QuotFollowUp",
        ["quotId"],
    )
    op.create_index(
        "ix_quotfollowup_company",
        "QuotFollowUp",
        ["companyId"],
    )


def downgrade() -> None:
    op.drop_index("ix_quotfollowup_company", table_name="QuotFollowUp")
    op.drop_index("ix_quotfollowup_quotid", table_name="QuotFollowUp")
    op.drop_table("QuotFollowUp")
