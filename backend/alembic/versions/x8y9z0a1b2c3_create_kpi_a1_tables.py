"""Create KPI Studio Phase A1 tables: definition, version, query run

Owned by ``kpi_studio``. Models in ``backend/kpi_studio/models.py``.

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "x8y9z0a1b2c3"
down_revision: Union[str, None] = "w7x8y9z0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- kpi_definition --------------------------------------------------
    op.create_table(
        "kpi_definition",
        sa.Column("kpi_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        # FK added with use_alter via separate ALTER below — kpi_version doesn't exist yet.
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_kpi_def_company_active", "kpi_definition", ["company_id", "is_active"])
    op.create_index("ix_kpi_def_owner", "kpi_definition", ["owner_user_id"])

    # ---- kpi_version -----------------------------------------------------
    op.create_table(
        "kpi_version",
        sa.Column("version_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "kpi_id", sa.Integer(),
            sa.ForeignKey("kpi_definition.kpi_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("database_key", sa.String(length=64), nullable=False, server_default="primary"),
        sa.Column("chart_config", sa.JSON(), nullable=False),
        sa.Column("params_schema", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_kpi_version_kpi_no", "kpi_version", ["kpi_id", "version_no"])

    # Now wire kpi_definition.current_version_id → kpi_version.version_id.
    op.create_foreign_key(
        "fk_kpi_def_current_version",
        "kpi_definition", "kpi_version",
        ["current_version_id"], ["version_id"],
    )

    # ---- kpi_query_run ---------------------------------------------------
    op.create_table(
        "kpi_query_run",
        sa.Column("run_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "kpi_version_id", sa.Integer(),
            sa.ForeignKey("kpi_version.version_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="preview"),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_kpi_run_company_started", "kpi_query_run", ["company_id", "started_at"])
    op.create_index("ix_kpi_run_user_started", "kpi_query_run", ["user_id", "started_at"])
    op.create_index("ix_kpi_run_version", "kpi_query_run", ["kpi_version_id"])


def downgrade() -> None:
    op.drop_index("ix_kpi_run_version", table_name="kpi_query_run")
    op.drop_index("ix_kpi_run_user_started", table_name="kpi_query_run")
    op.drop_index("ix_kpi_run_company_started", table_name="kpi_query_run")
    op.drop_table("kpi_query_run")

    op.drop_constraint("fk_kpi_def_current_version", "kpi_definition", type_="foreignkey")

    op.drop_index("ix_kpi_version_kpi_no", table_name="kpi_version")
    op.drop_table("kpi_version")

    op.drop_index("ix_kpi_def_owner", table_name="kpi_definition")
    op.drop_index("ix_kpi_def_company_active", table_name="kpi_definition")
    op.drop_table("kpi_definition")
