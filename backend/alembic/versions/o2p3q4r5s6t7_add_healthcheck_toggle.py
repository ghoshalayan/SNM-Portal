"""Add kill-switch for the automatic provider healthcheck (T-004).

One column: ``kpi_settings.healthcheck_auto_enabled BIT NULL``. When
False, the PUT /settings handler skips the healthcheck (so saves can't
be rolled back by a probe failure) AND the weekly
``provider_healthcheck`` scheduled job becomes a no-op (so the LLM
billing stops accruing recurring cost).

Nullable + default-resolved-by-code so existing rows continue to
work in "auto-on" mode until the admin explicitly flips it off via
the Health tab.

Idempotent — probes the column before adding.

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-05-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o2p3q4r5s6t7"
down_revision: Union[str, None] = "n1o2p3q4r5s6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "kpi_settings", "healthcheck_auto_enabled"):
        op.add_column(
            "kpi_settings",
            sa.Column("healthcheck_auto_enabled", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    try:
        op.drop_column("kpi_settings", "healthcheck_auto_enabled")
    except Exception:
        pass
