"""Widen tncDescription to NVARCHAR(MAX) on TermsNConditionMaster and QuotTermsNConditions

Supports up to 5000 words (~30K chars).

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-04-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "j4k5l6m7n8o9"
down_revision: Union[str, None] = "i3j4k5l6m7n8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "TermsNConditionMaster",
        "tncDescription",
        type_=sa.Text,
        existing_type=sa.String(500),
        existing_nullable=True,
    )
    op.alter_column(
        "QuotTermsNConditions",
        "tncDescription",
        type_=sa.Text,
        existing_type=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "QuotTermsNConditions",
        "tncDescription",
        type_=sa.String(500),
        existing_type=sa.Text,
        existing_nullable=True,
    )
    op.alter_column(
        "TermsNConditionMaster",
        "tncDescription",
        type_=sa.String(500),
        existing_type=sa.Text,
        existing_nullable=True,
    )
