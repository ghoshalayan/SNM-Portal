"""Add outcome column to QuotActivityLog

Each activity row now records both the quotation stage (status) and whether
the action succeeded or failed (outcome). Existing rows are backfilled to
'Success' — they were created from success-only logging calls before this
migration.

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-04-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "t4u5v6w7x8y9"
down_revision: Union[str, None] = "s3t4u5v6w7x8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "QuotActivityLog",
        sa.Column("outcome", sa.String(20), nullable=False, server_default="Success"),
    )


def downgrade() -> None:
    op.drop_column("QuotActivityLog", "outcome")
