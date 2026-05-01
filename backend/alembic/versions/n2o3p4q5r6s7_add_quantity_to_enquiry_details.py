"""Add quantity column to CustomerEnquiryDetails

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-04-02 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'n2o3p4q5r6s7'
down_revision: Union[str, None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('CustomerEnquiryDetails', sa.Column('quantity', sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('CustomerEnquiryDetails', 'quantity')
