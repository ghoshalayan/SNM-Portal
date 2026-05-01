"""Add CanEditNumber to RoleMenuMap

Revision ID: c7d8e9f0g1h2
Revises: b6c7d8e9f0g1
Create Date: 2026-04-12

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c7d8e9f0g1h2"
down_revision: Union[str, None] = "b6c7d8e9f0g1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "RoleMenuMap",
        sa.Column("CanEditNumber", sa.Boolean, server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("RoleMenuMap", "CanEditNumber")
