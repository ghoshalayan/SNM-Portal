"""Add icon, animations, filters_json to kpi_dashboard_item (Phase J.2 — AI Polish)

Per-dashboard-item visual + filter overrides — the AI Polish action
proposes these alongside the layout. Same row-level overrides we
already do for ``title_override`` and the ``grid_*`` coords:

* ``icon``           — Material icon name shown next to the title.
* ``animation_in``   — entry animation: fade | slide | scale | none.
* ``animation_out``  — exit animation, same vocabulary.
* ``filters_json``   — list of BuilderFilter dicts merged with the KPI's
                       own filters at execute time. Lets the same KPI
                       appear on two boards filtered to different slices
                       without forking the definition.

All four are nullable so existing rows survive without a backfill —
the API treats NULL as "no override" and the card renders unchanged.

Revision ID: j1k2l3m4n5o6
Revises: h7i8j9k0l1m2
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "h7i8j9k0l1m2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("kpi_dashboard_item", sa.Column("icon", sa.String(64), nullable=True))
    op.add_column("kpi_dashboard_item", sa.Column("animation_in", sa.String(16), nullable=True))
    op.add_column("kpi_dashboard_item", sa.Column("animation_out", sa.String(16), nullable=True))
    # JSON column — driver-portable type. SQL Server stores as NVARCHAR(MAX);
    # SQLite stores as TEXT. Both round-trip dict ↔ JSON cleanly.
    op.add_column("kpi_dashboard_item", sa.Column("filters_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("kpi_dashboard_item", "filters_json")
    op.drop_column("kpi_dashboard_item", "animation_out")
    op.drop_column("kpi_dashboard_item", "animation_in")
    op.drop_column("kpi_dashboard_item", "icon")
