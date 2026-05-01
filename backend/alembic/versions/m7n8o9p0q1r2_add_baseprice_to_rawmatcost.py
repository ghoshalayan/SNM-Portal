"""Add isBasePrice and diffFromBase to RawMaterialCost

Revision ID: m7n8o9p0q1r2
Revises: l6m7n8o9p0q1
Create Date: 2026-04-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "m7n8o9p0q1r2"
down_revision: Union[str, None] = "l6m7n8o9p0q1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("RawMaterialCost", sa.Column("isBasePrice", sa.Boolean, server_default=sa.text("0"), nullable=False))
    op.add_column("RawMaterialCost", sa.Column("diffFromBase", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("RawMaterialCost", "diffFromBase")
    op.drop_column("RawMaterialCost", "isBasePrice")
