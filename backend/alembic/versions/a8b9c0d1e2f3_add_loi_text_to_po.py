"""Add loiText column to QuotPurchaseOrder.

Phase 1H (Convert-as-LOI follow-up): the Convert action can now capture
either a formal PO or a Letter of Intent. LOIs carry an optional
free-text body — the intent / scope language the customer sent —
stored in this column. Nullable; only populated when ``isLOI = True``.

Revision ID: a8b9c0d1e2f3
Revises: z7a8b9c0d1e2
Create Date: 2026-05-18 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "z7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column("loiText", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("QuotPurchaseOrder", "loiText")
