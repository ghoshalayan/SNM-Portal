"""Create kpi_settings table (runtime-editable LLM + agent caps)

Single global row, written by the Settings page. When a column is
non-null, takes precedence over the matching ``KPI_*`` env var.
Plain-text ``openai_api_key`` for now; the API never returns it after
write.

Revision ID: d4e5f6h7i8j9
Revises: c3d4e5f6h7i8
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6h7i8j9"
down_revision: Union[str, None] = "c3d4e5f6h7i8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_settings",
        sa.Column("settings_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("llm_provider", sa.String(length=40), nullable=True),
        sa.Column("openai_api_key", sa.Text(), nullable=True),
        sa.Column("openai_model", sa.String(length=100), nullable=True),
        sa.Column("openai_base_url", sa.String(length=500), nullable=True),
        sa.Column("token_budget", sa.Integer(), nullable=True),
        sa.Column("max_iterations", sa.Integer(), nullable=True),
        sa.Column("max_tokens_per_call", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("kpi_settings")
