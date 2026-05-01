"""Create KPI Studio Phase A2 tables: dashboard, dashboard item

Owned by ``kpi_studio``. Models in ``backend/kpi_studio/models.py``.

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "y9z0a1b2c3d4"
down_revision: Union[str, None] = "x8y9z0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- kpi_dashboard ---------------------------------------------------
    op.create_table(
        "kpi_dashboard",
        sa.Column("dashboard_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="user"),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_kpi_dashboard_company_scope", "kpi_dashboard", ["company_id", "scope"])
    op.create_index("ix_kpi_dashboard_owner", "kpi_dashboard", ["owner_user_id"])

    # ---- kpi_dashboard_item ---------------------------------------------
    op.create_table(
        "kpi_dashboard_item",
        sa.Column("item_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "dashboard_id", sa.Integer(),
            sa.ForeignKey("kpi_dashboard.dashboard_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kpi_id", sa.Integer(),
            sa.ForeignKey("kpi_definition.kpi_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_class", sa.String(length=8), nullable=False, server_default="md"),
        sa.Column("title_override", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_kpi_dashboard_item_dash_pos",
        "kpi_dashboard_item",
        ["dashboard_id", "position"],
    )


def downgrade() -> None:
    op.drop_index("ix_kpi_dashboard_item_dash_pos", table_name="kpi_dashboard_item")
    op.drop_table("kpi_dashboard_item")
    op.drop_index("ix_kpi_dashboard_owner", table_name="kpi_dashboard")
    op.drop_index("ix_kpi_dashboard_company_scope", table_name="kpi_dashboard")
    op.drop_table("kpi_dashboard")
