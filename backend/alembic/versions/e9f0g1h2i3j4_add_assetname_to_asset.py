"""Add assetName to Asset

Revision ID: e9f0g1h2i3j4
Revises: d8e9f0g1h2i3
Create Date: 2026-04-12

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e9f0g1h2i3j4"
down_revision: Union[str, None] = "d8e9f0g1h2i3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "Asset",
        sa.Column("assetName", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("Asset", "assetName")
