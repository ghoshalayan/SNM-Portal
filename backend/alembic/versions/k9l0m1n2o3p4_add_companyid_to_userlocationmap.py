"""Add companyId to UserLocationMap

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
Create Date: 2026-04-01 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'k9l0m1n2o3p4'
down_revision: Union[str, None] = 'j8k9l0m1n2o3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add companyId column (nullable first to backfill existing rows)
    op.add_column(
        'UserLocationMap',
        sa.Column('companyId', sa.Integer(), nullable=True),
    )

    # Backfill companyId from the user's primary company
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE ulm SET ulm.companyId = u.companyId "
            "FROM UserLocationMap ulm "
            "INNER JOIN UserMaster u ON ulm.userId = u.userId "
            "WHERE ulm.companyId IS NULL"
        )
    )

    # Make non-nullable and add FK
    op.alter_column(
        'UserLocationMap',
        'companyId',
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        'fk_userlocationmap_companyid',
        'UserLocationMap',
        'Company',
        ['companyId'],
        ['companyId'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_userlocationmap_companyid', 'UserLocationMap', type_='foreignkey')
    op.drop_column('UserLocationMap', 'companyId')
