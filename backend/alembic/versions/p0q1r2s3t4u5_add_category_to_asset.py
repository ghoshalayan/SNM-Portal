"""Add category to Asset

Used to distinguish general attachments ('general', default) from specialized
kinds (e.g. 'po_document' for Customer PO scans uploaded from the Mature-quotation
flow). Keeping a single Asset table with a discriminator column lets the /assets
endpoints serve all cases — callers filter by category when they want a specific
subset.

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-04-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "p0q1r2s3t4u5"
down_revision: Union[str, None] = "o9p0q1r2s3t4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "Asset",
        sa.Column("category", sa.String(30), nullable=True),
    )
    # Existing rows are 'general' by convention (NULL is also treated as general
    # by the API). We do NOT backfill to keep the migration fast on large tables.


def downgrade() -> None:
    op.drop_column("Asset", "category")
