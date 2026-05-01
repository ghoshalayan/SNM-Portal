"""create FinancialYear table

Revision ID: v0w1x2y3z4a5
Revises: u9v0w1x2y3z4
Create Date: 2026-04-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "v0w1x2y3z4a5"
down_revision: Union[str, None] = "u9v0w1x2y3z4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "FinancialYear",
        sa.Column("fyId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("fyName", sa.String(100), nullable=False),
        sa.Column("fyCode", sa.String(50), nullable=False),
        sa.Column("isCurrent", sa.Boolean, server_default=sa.text("0"), nullable=False),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
        sa.Column("isActive", sa.Boolean, server_default=sa.text("1"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("FinancialYear")
