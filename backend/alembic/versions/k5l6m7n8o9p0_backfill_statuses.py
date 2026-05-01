"""Backfill NULL/legacy statuses to new defaults

- QuotSummary: NULL/empty → 'Draft'
- CustomerEnquiry: NULL/'Open'/empty → 'New'
- Enquiries that already have quotations → 'Quotation Prepared'

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-04-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "k5l6m7n8o9p0"
down_revision: Union[str, None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Quotations: NULL/empty → 'Draft'
    op.execute("""
        UPDATE QuotSummary
        SET status = 'Draft'
        WHERE status IS NULL OR status = '' OR status = 'Open'
    """)

    # Enquiries: NULL/'Open'/empty → 'New'
    op.execute("""
        UPDATE CustomerEnquiry
        SET status = 'New'
        WHERE status IS NULL OR status = '' OR status = 'Open'
    """)

    # Enquiries that have at least one quotation → 'Quotation Prepared'
    op.execute("""
        UPDATE CustomerEnquiry
        SET status = 'Quotation Prepared'
        WHERE status = 'New'
          AND enqid IN (
            SELECT DISTINCT enqid FROM QuotSummary
            WHERE enqid IS NOT NULL AND isActive = 1
          )
    """)


def downgrade() -> None:
    # Revert is intentionally a no-op — status data was corrected
    pass
