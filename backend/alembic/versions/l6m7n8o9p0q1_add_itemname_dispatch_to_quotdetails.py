"""Add itemName and modeOfDispatch to QuotDetails

Revision ID: l6m7n8o9p0q1
Revises: k5l6m7n8o9p0
Create Date: 2026-04-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "l6m7n8o9p0q1"
down_revision: Union[str, None] = "k5l6m7n8o9p0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("QuotDetails", sa.Column("itemName", sa.String(200), nullable=True))
    op.add_column("QuotDetails", sa.Column("modeOfDispatch", sa.String(200), nullable=True))

    # Backfill itemName from ItemName table where itemid is set
    op.execute("""
        UPDATE QuotDetails
        SET itemName = i.itemName
        FROM QuotDetails qd
        INNER JOIN ItemName i ON i.itemId = qd.itemid
        WHERE qd.itemName IS NULL AND qd.itemid IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_column("QuotDetails", "modeOfDispatch")
    op.drop_column("QuotDetails", "itemName")
