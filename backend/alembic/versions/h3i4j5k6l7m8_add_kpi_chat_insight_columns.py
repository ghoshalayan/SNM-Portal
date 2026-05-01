"""Add insight + recommendations to kpi_chat_message (Phase B3)

A second LLM pass reads the executed result + chart and produces a short
narrative + a list of follow-up recommendations. Both stored alongside
the existing assistant fields. Nullable — graceful degrade when the
insight pass is disabled or fails.

Revision ID: h3i4j5k6l7m8
Revises: g7h8i9j0k1l2
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kpi_chat_message",
        sa.Column("insight", sa.Text(), nullable=True),
    )
    op.add_column(
        "kpi_chat_message",
        sa.Column("recommendations", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kpi_chat_message", "recommendations")
    op.drop_column("kpi_chat_message", "insight")
