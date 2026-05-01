"""Create kpi_chat_session + kpi_chat_message (Phase B1)

Persistent chat history for the smart-analysis chatbot. Sessions are
per-user, not shared. Messages cascade-delete with their session. The
``rolling_summary`` column on the session is reserved for B3 — empty
for now.

Revision ID: f6h7i8j9k0l1
Revises: e5f6h7i8j9k0
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6h7i8j9k0l1"
down_revision: Union[str, None] = "e5f6h7i8j9k0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_chat_session",
        sa.Column("chat_session_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("rolling_summary", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_kpi_chat_session_user_updated", "kpi_chat_session", ["user_id", "updated_at"])
    op.create_index("ix_kpi_chat_session_active", "kpi_chat_session", ["user_id", "is_active"])

    op.create_table(
        "kpi_chat_message",
        sa.Column("chat_message_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "chat_session_id", sa.Integer(),
            sa.ForeignKey("kpi_chat_session.chat_session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("sql", sa.Text(), nullable=True),
        sa.Column("rewritten_sql", sa.Text(), nullable=True),
        sa.Column("result_columns", sa.JSON(), nullable=True),
        sa.Column("result_rows", sa.JSON(), nullable=True),
        sa.Column("chart_config", sa.JSON(), nullable=True),
        sa.Column("agent_steps", sa.JSON(), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_kpi_chat_message_session", "kpi_chat_message",
        ["chat_session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_kpi_chat_message_session", table_name="kpi_chat_message")
    op.drop_table("kpi_chat_message")
    op.drop_index("ix_kpi_chat_session_active", table_name="kpi_chat_session")
    op.drop_index("ix_kpi_chat_session_user_updated", table_name="kpi_chat_session")
    op.drop_table("kpi_chat_session")
