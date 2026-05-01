"""Create kpi_table_relationship (Phase F — data modeling)

A directional join edge between two tables. Compilers walk these to
auto-emit LEFT JOINs in Power BI–style "drag related column"
authoring; auto-detected from FK metadata at first sight, plus
user-managed manual rows.

Revision ID: h7i8j9k0l1m2
Revises: h5i6j7k8l9m0
Create Date: 2026-04-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h7i8j9k0l1m2"
# Chain off the kpi_studio grid migration (the Phase D head) so the
# kpi_studio branch advances cleanly. The original draft listed
# h6i7j8k9l0m1 (a host-app user_location migration) as the parent —
# that left h5 orphaned and produced two heads.
down_revision: Union[str, None] = "h5i6j7k8l9m0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_table_relationship",
        sa.Column("relationship_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("from_schema", sa.String(length=64), nullable=True),
        sa.Column("from_table", sa.String(length=128), nullable=False),
        sa.Column("from_column", sa.String(length=128), nullable=False),
        sa.Column("to_schema", sa.String(length=64), nullable=True),
        sa.Column("to_table", sa.String(length=128), nullable=False),
        sa.Column("to_column", sa.String(length=128), nullable=False),
        sa.Column("cardinality", sa.String(length=20), nullable=False, server_default="many_to_one"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="auto"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_kpi_relationship_from", "kpi_table_relationship",
        ["from_table", "from_column"],
    )
    op.create_index(
        "ix_kpi_relationship_to", "kpi_table_relationship",
        ["to_table", "to_column"],
    )
    op.create_index(
        "ix_kpi_relationship_company", "kpi_table_relationship",
        ["company_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_kpi_relationship_company", table_name="kpi_table_relationship")
    op.drop_index("ix_kpi_relationship_to", table_name="kpi_table_relationship")
    op.drop_index("ix_kpi_relationship_from", table_name="kpi_table_relationship")
    op.drop_table("kpi_table_relationship")
