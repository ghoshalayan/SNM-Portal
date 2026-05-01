"""Add peerAccess column to RoleMaster

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
Create Date: 2026-04-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "y3z4a5b6c7d8"
down_revision: Union[str, None] = "x2y3z4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "RoleMaster",
        sa.Column("peerAccess", sa.Boolean, server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("RoleMaster", "peerAccess")
