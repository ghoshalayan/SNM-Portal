"""Make districtid nullable in UserLocationMap

Revision ID: j8k9l0m1n2o3
Revises: i7j8k9l0m1n2
Create Date: 2026-04-01 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'j8k9l0m1n2o3'
down_revision: Union[str, None] = 'i7j8k9l0m1n2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'UserLocationMap',
        'districtid',
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Remove rows with NULL districtid before making non-nullable
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM UserLocationMap WHERE districtid IS NULL")
    )
    op.alter_column(
        'UserLocationMap',
        'districtid',
        existing_type=sa.Integer(),
        nullable=False,
    )
