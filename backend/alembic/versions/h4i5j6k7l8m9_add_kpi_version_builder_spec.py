"""Add builder_spec to kpi_version (Phase C — Smart Builder)

When the user authors a KPI via the drag-fields-into-wells UI, this
column holds the spec that drove the compile. ``query_text`` becomes a
derived value — recompiled from the spec on every save — so editing
round-trips losslessly. ``None`` keeps the legacy raw-SQL path working
unchanged.

Revision ID: h4i5j6k7l8m9
Revises: h3i4j5k6l7m8
Create Date: 2026-04-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h4i5j6k7l8m9"
down_revision: Union[str, None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kpi_version",
        sa.Column("builder_spec", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kpi_version", "builder_spec")
