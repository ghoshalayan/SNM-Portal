"""Create CostTemplate table

Revision ID: b6c7d8e9f0g1
Revises: a5b6c7d8e9f0
Create Date: 2026-04-11

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b6c7d8e9f0g1"
down_revision: Union[str, None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COST_FIELDS = [
    "Marketing", "FreightTrailer", "FreightTruck", "Unloading", "OHD", "IFC",
    "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge", "ShortLnthCharge",
    "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation", "Commission", "Misc",
    "Testing", "MOUTOD", "SplDisc", "JC",
]


def upgrade() -> None:
    columns = [
        sa.Column("templateId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("templateName", sa.String(200), nullable=False),
    ]
    for f in COST_FIELDS:
        columns.append(sa.Column(f, sa.Numeric(18, 2), nullable=True))
    columns += [
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
        sa.Column("isActive", sa.Boolean, server_default=sa.text("1"), nullable=False),
    ]
    op.create_table("CostTemplate", *columns)


def downgrade() -> None:
    op.drop_table("CostTemplate")
