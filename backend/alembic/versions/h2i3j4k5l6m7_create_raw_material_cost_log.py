"""Create RawMaterialCostLog table

Append-only audit log capturing every update to RawMaterialCost.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-04-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "RawMaterialCostLog",
        sa.Column("logId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rawMaterialCostId", sa.Integer,
                  sa.ForeignKey("RawMaterialCost.rawMaterialCostId"), nullable=False),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("dia", sa.String(50), nullable=False),
        sa.Column("oldCost", sa.Numeric(18, 2), nullable=True),
        sa.Column("newCost", sa.Numeric(18, 2), nullable=False),
        sa.Column("oldEffectedFrom", sa.DateTime, nullable=True),
        sa.Column("newEffectedFrom", sa.DateTime, nullable=True),
        sa.Column("action", sa.String(20), nullable=False, server_default=sa.text("'UPDATE'")),
        sa.Column("remarks", sa.String(500), nullable=True),
        sa.Column("changedBy", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("changedOn", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_rawmatcostlog_cost_date",
        "RawMaterialCostLog",
        ["rawMaterialCostId", "changedOn"],
    )
    op.create_index(
        "ix_rawmatcostlog_company",
        "RawMaterialCostLog",
        ["companyId"],
    )


def downgrade() -> None:
    op.drop_index("ix_rawmatcostlog_company", table_name="RawMaterialCostLog")
    op.drop_index("ix_rawmatcostlog_cost_date", table_name="RawMaterialCostLog")
    op.drop_table("RawMaterialCostLog")
