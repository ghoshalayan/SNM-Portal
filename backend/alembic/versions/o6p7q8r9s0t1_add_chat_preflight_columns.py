"""Add chat-preflight columns

Two adjacent changes that travel together:

1. ``KpiChatMessage.kind`` — small string discriminator. Existing rows
   default to ``'answer'`` (the canonical successful-query turn). The
   pre-flight loop introduces ``'clarify'`` (an agent-to-user question
   when the Planner can't disambiguate from context alone). Future
   work may add ``'reject'`` / ``'plan'`` etc. without further DDL.

2. ``KpiSettings`` knobs that govern the new Planner/Resolver loop:
   - ``preflight_enabled`` — kill switch (default ON via Python-side
     resolution; column nullable for back-compat with rows pre-dating
     this migration).
   - ``preflight_max_rounds`` — cap on Planner ↔ Resolver bounces per
     turn (default 5; user spec'd 5–10 as the acceptable range).
   - ``preflight_user_escalations`` — cap on consecutive user-clarify
     turns before auto-promoting to ``ready`` (default 2).

Revision ID: o6p7q8r9s0t1
Revises: n5o6p7q8r9s0
Create Date: 2026-05-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o6p7q8r9s0t1"
down_revision: Union[str, None] = "n5o6p7q8r9s0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill 'answer' so existing rows have a valid kind. Drop the
    # default after the column is populated — Python-side default takes
    # over for new inserts.
    op.add_column(
        "kpi_chat_message",
        sa.Column(
            "kind",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'answer'"),
        ),
    )
    op.alter_column("kpi_chat_message", "kind", server_default=None)

    op.add_column(
        "kpi_settings",
        sa.Column("preflight_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "kpi_settings",
        sa.Column("preflight_max_rounds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "kpi_settings",
        sa.Column("preflight_user_escalations", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kpi_settings", "preflight_user_escalations")
    op.drop_column("kpi_settings", "preflight_max_rounds")
    op.drop_column("kpi_settings", "preflight_enabled")
    op.drop_column("kpi_chat_message", "kind")
