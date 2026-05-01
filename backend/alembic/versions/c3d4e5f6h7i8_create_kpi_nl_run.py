"""Create kpi_nl_run audit table (KPI Studio Phase A7)

One row per NL→SQL agent invocation. Captures the full step timeline
as JSON so an operator can replay an agent run and spot prompt or
schema-context issues. Phase B chat will reuse this table with
``surface='chat'``.

Revision ID: c3d4e5f6h7i8
Revises: b2c3d4e5f6h7
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6h7i8"
down_revision: Union[str, None] = "b2c3d4e5f6h7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_nl_run",
        sa.Column("nl_run_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("surface", sa.String(length=20), nullable=False, server_default="editor"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("final_sql", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("iterations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_kpi_nl_run_company_started", "kpi_nl_run", ["company_id", "started_at"])
    op.create_index("ix_kpi_nl_run_user_started", "kpi_nl_run", ["user_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_kpi_nl_run_user_started", table_name="kpi_nl_run")
    op.drop_index("ix_kpi_nl_run_company_started", table_name="kpi_nl_run")
    op.drop_table("kpi_nl_run")
