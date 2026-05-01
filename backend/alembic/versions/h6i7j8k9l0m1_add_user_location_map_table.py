"""Add UserLocationMap table for user-to-location mapping

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2026-03-31 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'h6i7j8k9l0m1'
down_revision: Union[str, None] = 'g5h6i7j8k9l0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'UserLocationMap',
        sa.Column('userLocationMapId', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('userId', sa.Integer(), sa.ForeignKey('UserMaster.userId'), nullable=False),
        sa.Column('countryid', sa.Integer(), sa.ForeignKey('Country.countryid'), nullable=False),
        sa.Column('stateid', sa.Integer(), sa.ForeignKey('StateMaster.stateid'), nullable=False),
        sa.Column('districtid', sa.Integer(), sa.ForeignKey('DistrictMaster.districtid'), nullable=False),
        sa.Column('createdon', sa.DateTime(), nullable=True),
        sa.Column('createdby', sa.Integer(), nullable=True),
        sa.Column('lastupdateon', sa.DateTime(), nullable=True),
        sa.Column('lastupdateby', sa.Integer(), nullable=True),
        sa.Column('isActive', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.PrimaryKeyConstraint('userLocationMapId'),
    )


def downgrade() -> None:
    op.drop_table('UserLocationMap')
