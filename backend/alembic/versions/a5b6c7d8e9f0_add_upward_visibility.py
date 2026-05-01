"""Add upwardVisibilityLevels to RoleMaster

Revision ID: a5b6c7d8e9f0
Revises: z4a5b6c7d8e9
Create Date: 2026-04-11

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "z4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "RoleMaster",
        sa.Column("upwardVisibilityLevels", sa.Integer, server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("RoleMaster", "upwardVisibilityLevels")
