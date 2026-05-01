"""Create kpi_schema_snapshot (KPI Studio Phase 1)

This migration is owned by the ``kpi_studio`` package. The table itself is
declared in ``backend/kpi_studio/models.py`` (separate Base) but lives in
the same database for now. If/when ``kpi_studio`` is extracted to its own
repo, this file moves with it.

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w7x8y9z0a1b2"
down_revision: Union[str, None] = "v6w7x8y9z0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_schema_snapshot",
        sa.Column("snapshot_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("database_key", sa.String(length=64), nullable=False, server_default="primary"),
        # SQL Server has no native JSON type; SQLAlchemy maps JSON to NVARCHAR(MAX).
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relationship_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index(
        "ix_kpi_schema_snapshot_current",
        "kpi_schema_snapshot",
        ["database_key", "is_current"],
    )


def downgrade() -> None:
    op.drop_index("ix_kpi_schema_snapshot_current", table_name="kpi_schema_snapshot")
    op.drop_table("kpi_schema_snapshot")
