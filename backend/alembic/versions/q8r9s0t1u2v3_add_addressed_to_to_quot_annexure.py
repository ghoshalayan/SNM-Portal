"""Add ``addressedTo`` column to QuotAnnexure.

The "To:" line on the printed annexure was previously hardcoded in the
print template (``Mr. A. Chaudhuri / Mrs. S. Basu Sengupta``). Promoted
to an editable column so:

* Each company can set its own addressee.
* KROs can override per annexure when the addressee differs.

Existing active annexures are backfilled with the legacy hardcoded
value so their printed copies remain unchanged.

Revision ID: q8r9s0t1u2v3
Revises: p7q8r9s0t1u2
Create Date: 2026-05-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "q8r9s0t1u2v3"
down_revision: Union[str, None] = "p7q8r9s0t1u2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_ADDRESSEE = "Mr. A. Chaudhuri / Mrs. S. Basu Sengupta"


def upgrade() -> None:
    op.add_column(
        "QuotAnnexure",
        sa.Column("addressedTo", sa.String(length=300), nullable=True),
    )
    # Backfill existing active rows with the legacy addressee so old
    # annexures keep printing the same name. Inactive (soft-deleted)
    # rows stay null — they're not user-visible anyway.
    op.execute(
        """
        UPDATE QuotAnnexure
        SET addressedTo = :addr
        WHERE isActive = 1 AND addressedTo IS NULL
        """.replace(":addr", f"N'{_LEGACY_ADDRESSEE}'")
    )


def downgrade() -> None:
    op.drop_column("QuotAnnexure", "addressedTo")
