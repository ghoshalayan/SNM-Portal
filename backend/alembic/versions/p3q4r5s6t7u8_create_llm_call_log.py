"""Create kpi_llm_call_log + add call-logging toggle to kpi_settings.

Two changes in one migration:

1. New table ``kpi_llm_call_log`` — one row per outbound LLM HTTP call.
   Records request body, response body, model, provider, base URL,
   latency, token usage, correlation_id (groups calls fired during
   one user-facing operation), trigger_source. Authorization headers
   are masked by ``call_logger.py`` before persist; bodies capped at
   64 KB per side with a truncated flag.

2. Two columns on ``kpi_settings``:
   * ``call_logging_enabled`` BIT NULL — toggle for the whole logging
     subsystem. Nullable; null = default True via resolver.
   * ``call_log_retention_days`` INT NULL — pruning window for the
     scheduled cleanup job. Null = default 7.

Idempotent on both halves.

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-05-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p3q4r5s6t7u8"
down_revision: Union[str, None] = "o2p3q4r5s6t7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def _column_exists(bind, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ---- kpi_llm_call_log -----------------------------------------------
    if not _table_exists(bind, "kpi_llm_call_log"):
        op.create_table(
            "kpi_llm_call_log",
            sa.Column("call_log_id", sa.Integer(),
                      primary_key=True, autoincrement=True, nullable=False),
            sa.Column("correlation_id", sa.String(length=40), nullable=True),
            sa.Column("trigger_source", sa.String(length=40),
                      nullable=False, server_default="unknown"),
            sa.Column("trigger_ref_kind", sa.String(length=40), nullable=True),
            sa.Column("trigger_ref_id", sa.Integer(), nullable=True),
            sa.Column("company_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column(
                "provider_config_id", sa.Integer(),
                sa.ForeignKey("kpi_llm_provider_config.provider_config_id",
                              ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("provider_kind", sa.String(length=40), nullable=False),
            sa.Column("provider_label", sa.String(length=200), nullable=True),
            sa.Column("base_url", sa.String(length=500), nullable=False),
            sa.Column("model", sa.String(length=200), nullable=False),
            sa.Column("stage_key", sa.String(length=40), nullable=True),
            sa.Column("request_method", sa.String(length=10),
                      nullable=False, server_default="POST"),
            sa.Column("request_path", sa.String(length=200), nullable=False),
            sa.Column("request_body", sa.Text(), nullable=True),
            sa.Column("request_headers", sa.Text(), nullable=True),
            sa.Column("request_truncated", sa.Boolean(),
                      nullable=False, server_default=sa.text("0")),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("response_body", sa.Text(), nullable=True),
            sa.Column("response_truncated", sa.Boolean(),
                      nullable=False, server_default=sa.text("0")),
            sa.Column("succeeded", sa.Boolean(),
                      nullable=False, server_default=sa.text("0")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("latency_ms", sa.Integer(),
                      nullable=False, server_default="0"),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_kpi_llm_call_log_started",
                        "kpi_llm_call_log", ["started_at"])
        op.create_index("ix_kpi_llm_call_log_corr",
                        "kpi_llm_call_log", ["correlation_id"])
        op.create_index("ix_kpi_llm_call_log_provider",
                        "kpi_llm_call_log", ["provider_config_id", "started_at"])
        op.create_index("ix_kpi_llm_call_log_source",
                        "kpi_llm_call_log", ["trigger_source", "started_at"])

    # ---- kpi_settings columns -------------------------------------------
    if not _column_exists(bind, "kpi_settings", "call_logging_enabled"):
        op.add_column(
            "kpi_settings",
            sa.Column("call_logging_enabled", sa.Boolean(), nullable=True),
        )
    if not _column_exists(bind, "kpi_settings", "call_log_retention_days"):
        op.add_column(
            "kpi_settings",
            sa.Column("call_log_retention_days", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    for col in ("call_log_retention_days", "call_logging_enabled"):
        try:
            op.drop_column("kpi_settings", col)
        except Exception:
            pass
    try:
        op.drop_table("kpi_llm_call_log")
    except Exception:
        pass
