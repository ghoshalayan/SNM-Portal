"""Add grid_x/y/w/h to kpi_dashboard_item (Phase D — Power BI grid)

Replaces the coarse ``position`` + ``size_class`` placement with a true
free-form grid: each tile holds a (x, y, w, h) rectangle on a 12-column
grid. The legacy columns stay for back-compat — the API backfills grid
coordinates from them when a row's grid_* values are NULL, so existing
dashboards keep rendering without a manual data fix.

Revision ID: h5i6j7k8l9m0
Revises: h4i5j6k7l8m9
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h5i6j7k8l9m0"
down_revision: Union[str, None] = "h4i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kpi_dashboard_item", sa.Column("grid_x", sa.Integer(), nullable=True))
    op.add_column("kpi_dashboard_item", sa.Column("grid_y", sa.Integer(), nullable=True))
    op.add_column("kpi_dashboard_item", sa.Column("grid_w", sa.Integer(), nullable=True))
    op.add_column("kpi_dashboard_item", sa.Column("grid_h", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("kpi_dashboard_item", "grid_h")
    op.drop_column("kpi_dashboard_item", "grid_w")
    op.drop_column("kpi_dashboard_item", "grid_y")
    op.drop_column("kpi_dashboard_item", "grid_x")
