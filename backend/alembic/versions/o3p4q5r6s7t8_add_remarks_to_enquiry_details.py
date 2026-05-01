"""Add remarks column to CustomerEnquiryDetails

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-04-02 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'o3p4q5r6s7t8'
down_revision: Union[str, None] = 'n2o3p4q5r6s7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('CustomerEnquiryDetails', sa.Column('remarks', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('CustomerEnquiryDetails', 'remarks')
