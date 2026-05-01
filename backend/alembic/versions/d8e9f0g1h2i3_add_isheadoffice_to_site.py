"""Add isHeadOffice to CustomerSite

Revision ID: d8e9f0g1h2i3
Revises: c7d8e9f0g1h2
Create Date: 2026-04-12

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d8e9f0g1h2i3"
down_revision: Union[str, None] = "c7d8e9f0g1h2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "CustomerSite",
        sa.Column("isHeadOffice", sa.Boolean, server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("CustomerSite", "isHeadOffice")
