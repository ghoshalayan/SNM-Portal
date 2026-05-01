"""Add x_label, y_label to kpi_dashboard_item (Phase J.2 — AI Polish axis names)

Per-dashboard-item axis labels — AI Polish proposes these for bar /
line charts so a card can read "Sales by Region" with explicit
"Region" / "Sales (₹)" axes even though the underlying KPI's
chart_config has no labels set.

Both nullable. NULL means "no override" — the chart-renderer falls
back to the KPI's chart_config x_label / y_label (which themselves
fall back to no axis title). Existing rows survive without a
backfill.

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k2l3m4n5o6p7"
down_revision: Union[str, None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kpi_dashboard_item", sa.Column("x_label", sa.String(120), nullable=True))
    op.add_column("kpi_dashboard_item", sa.Column("y_label", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("kpi_dashboard_item", "y_label")
    op.drop_column("kpi_dashboard_item", "x_label")
