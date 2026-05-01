"""Create QuotActivityLog

Timewise audit log of quotation lifecycle events — Create, Approve, Reject,
Revise, Mature, Handover, Viability/Annexure Generate & Approve. Written
synchronously by each lifecycle endpoint so the log is the canonical record
of 'who did what when' regardless of later edits or deletes.

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-04-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "s3t4u5v6w7x8"
down_revision: Union[str, None] = "r2s3t4u5v6w7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "QuotActivityLog",
        sa.Column("logId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("quotId", sa.Integer, sa.ForeignKey("QuotSummary.quotId"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),       # e.g. 'Created', 'Approved', 'Matured'
        sa.Column("status", sa.String(50), nullable=True),         # quotation status AFTER the action
        sa.Column("details", sa.Text, nullable=True),              # free-text context (e.g. 'handover to X')
        sa.Column("actionOn", sa.DateTime, nullable=False),
        sa.Column("actionByUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("actionByName", sa.String(200), nullable=True),  # snapshot
    )
    op.create_index(
        "IX_QuotActivityLog_quotId_actionOn",
        "QuotActivityLog",
        ["quotId", "actionOn"],
    )


def downgrade() -> None:
    op.drop_index("IX_QuotActivityLog_quotId_actionOn", table_name="QuotActivityLog")
    op.drop_table("QuotActivityLog")
