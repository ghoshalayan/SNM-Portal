"""Add OpenRouter extras + per-stage model routing to KpiSettings
(T-901 + T-902).

Four new columns on ``kpi_settings``:

* ``openrouter_referer``    — sent as ``HTTP-Referer`` for OpenRouter
                              routing fairness + analytics.
* ``openrouter_app_name``   — sent as ``X-Title``.
* ``stage_models``          — JSON map ``{stage_key: model_string}``;
                              T-902 per-stage routing.
* ``default_stage_model``   — fallback model when a stage isn't in
                              ``stage_models``.

All nullable. Existing rows continue to work unchanged — the
single-model-for-everything code path falls through when
``stage_models`` is empty.

Idempotent — probes ``INFORMATION_SCHEMA.COLUMNS`` before each
``add_column``.

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m0n1o2p3q4r5"
down_revision: Union[str, None] = "l9m0n1o2p3q4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = [
    ("openrouter_referer", sa.String(length=500)),
    ("openrouter_app_name", sa.String(length=200)),
    ("stage_models", sa.JSON()),
    ("default_stage_model", sa.String(length=200)),
]


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    for name, col_type in NEW_COLUMNS:
        if _column_exists(bind, "kpi_settings", name):
            continue
        op.add_column("kpi_settings", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    for name, _ in NEW_COLUMNS:
        try:
            op.drop_column("kpi_settings", name)
        except Exception:
            pass
