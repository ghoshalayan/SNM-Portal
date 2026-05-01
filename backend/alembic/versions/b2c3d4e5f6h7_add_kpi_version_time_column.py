"""Add KpiVersion.time_column (KPI Studio Phase A5)

Optional column name used by the time-period selector — when set, the
runtime can detect that this KPI participates in date filtering. The
actual filter clause lives inside the user's SQL via the safe-bound
``:start_date`` / ``:end_date`` placeholders.

Revision ID: b2c3d4e5f6h7
Revises: b1c2d3e4f5g6
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6h7"
down_revision: Union[str, None] = "b1c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kpi_version",
        sa.Column("time_column", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kpi_version", "time_column")
