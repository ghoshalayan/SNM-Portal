"""Add domain_knowledge column to kpi_settings

Plain-text admin-curated business context appended to the chatbot
agent's system prompt (System Knowledge Hub). Empty / null falls
back to no extras block.

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kpi_settings",
        sa.Column("domain_knowledge", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("kpi_settings", "domain_knowledge")
