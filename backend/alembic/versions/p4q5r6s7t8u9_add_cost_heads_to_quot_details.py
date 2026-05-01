"""Add cost head columns to QuotDetails

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-04-02 16:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'p4q5r6s7t8u9'
down_revision: Union[str, None] = 'o3p4q5r6s7t8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('QuotDetails', sa.Column('itemid', sa.Integer(), sa.ForeignKey('ItemName.itemId'), nullable=True))
    op.add_column('QuotDetails', sa.Column('TPWGST', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('Marketing', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('FreightTrailer', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('FreightTruck', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('Unloading', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('OHD', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('IFC', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('WeighmentDiff', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('CD', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('SWECharge', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('CRS', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('IncCharge', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('ShortLnthCharge', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('SpeciFicLnthCharge', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('ExtraCharge', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('Fluctuation', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('Commission', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('Misc', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('Testing', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('MOUTOD', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('SplDisc', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('JC', sa.Numeric(18, 2), nullable=True))
    op.add_column('QuotDetails', sa.Column('gstMode', sa.String(20), nullable=True, server_default='IGST'))


def downgrade() -> None:
    cols = [
        'itemid', 'TPWGST', 'Marketing', 'FreightTrailer', 'FreightTruck',
        'Unloading', 'OHD', 'IFC', 'WeighmentDiff', 'CD', 'SWECharge', 'CRS',
        'IncCharge', 'ShortLnthCharge', 'SpeciFicLnthCharge', 'ExtraCharge',
        'Fluctuation', 'Commission', 'Misc', 'Testing', 'MOUTOD', 'SplDisc',
        'JC', 'gstMode',
    ]
    for col in cols:
        op.drop_column('QuotDetails', col)
