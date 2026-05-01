"""Add status masters, communication tables, rename costing columns, add userDesignation

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
Create Date: 2026-04-02 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'l0m1n2o3p4q5'
down_revision: Union[str, None] = 'k9l0m1n2o3p4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === 1. New Tables ===

    # EnQStatusMaster
    op.create_table(
        'EnQStatusMaster',
        sa.Column('enqstatid', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('enqStatus', sa.String(50), nullable=False),
        sa.Column('stepno', sa.Integer, nullable=True),
        sa.Column('companyId', sa.Integer, sa.ForeignKey('Company.companyId'), nullable=False),
        sa.Column('createdon', sa.DateTime, server_default=sa.func.now()),
        sa.Column('createdby', sa.Integer, nullable=True),
        sa.Column('lastupdateon', sa.DateTime, nullable=True),
        sa.Column('lastupdateby', sa.Integer, nullable=True),
        sa.Column('isActive', sa.Boolean, server_default=sa.text('1'), nullable=False),
    )

    # QuotQStatusMaster
    op.create_table(
        'QuotQStatusMaster',
        sa.Column('quotstatid', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('quotStatus', sa.String(50), nullable=False),
        sa.Column('stepno', sa.Integer, nullable=True),
        sa.Column('companyId', sa.Integer, sa.ForeignKey('Company.companyId'), nullable=False),
        sa.Column('createdon', sa.DateTime, server_default=sa.func.now()),
        sa.Column('createdby', sa.Integer, nullable=True),
        sa.Column('lastupdateon', sa.DateTime, nullable=True),
        sa.Column('lastupdateby', sa.Integer, nullable=True),
        sa.Column('isActive', sa.Boolean, server_default=sa.text('1'), nullable=False),
    )

    # CommunicationMode
    op.create_table(
        'CommunicationMode',
        sa.Column('commmodeId', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('commmode', sa.String(50), nullable=False),
        sa.Column('companyId', sa.Integer, sa.ForeignKey('Company.companyId'), nullable=False),
        sa.Column('createdon', sa.DateTime, server_default=sa.func.now()),
        sa.Column('createdby', sa.Integer, nullable=True),
        sa.Column('lastupdateon', sa.DateTime, nullable=True),
        sa.Column('lastupdateby', sa.Integer, nullable=True),
        sa.Column('isActive', sa.Boolean, server_default=sa.text('1'), nullable=False),
    )

    # CommunicationLog
    op.create_table(
        'CommunicationLog',
        sa.Column('commlogID', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('commmode', sa.String(50), nullable=True),
        sa.Column('contactto', sa.String(100), nullable=True),
        sa.Column('contactinfo', sa.String(500), nullable=True),
        sa.Column('enqid', sa.Integer, sa.ForeignKey('CustomerEnquiry.enqid'), nullable=True),
        sa.Column('quoteid', sa.Integer, sa.ForeignKey('QuotSummary.quotId'), nullable=True),
        sa.Column('commsubject', sa.String(500), nullable=True),
        sa.Column('commdescription', sa.String(5000), nullable=True),
        sa.Column('companyId', sa.Integer, sa.ForeignKey('Company.companyId'), nullable=False),
        sa.Column('createdon', sa.DateTime, server_default=sa.func.now()),
        sa.Column('createdby', sa.Integer, nullable=True),
        sa.Column('lastupdateon', sa.DateTime, nullable=True),
        sa.Column('lastupdateby', sa.Integer, nullable=True),
        sa.Column('isActive', sa.Boolean, server_default=sa.text('1'), nullable=False),
    )

    # === 2. Add userDesignation to UserMaster ===
    op.add_column('UserMaster', sa.Column('userDesignation', sa.String(100), nullable=True))

    # === 3. Rename CustomerEnquiryCosting columns ===
    # [TPWoGST] -> Marketing
    op.alter_column('CustomerEnquiryCosting', 'TPWoGST', new_column_name='Marketing')
    # [costPoint1] -> FreightTrailer
    op.alter_column('CustomerEnquiryCosting', 'costPoint1', new_column_name='FreightTrailer')
    # [costPoint2] -> FreightTruck
    op.alter_column('CustomerEnquiryCosting', 'costPoint2', new_column_name='FreightTruck')
    # [costPoint3] -> Unloading
    op.alter_column('CustomerEnquiryCosting', 'costPoint3', new_column_name='Unloading')
    # [costPoint4] -> OHD
    op.alter_column('CustomerEnquiryCosting', 'costPoint4', new_column_name='OHD')
    # [costPoint5] -> IFC
    op.alter_column('CustomerEnquiryCosting', 'costPoint5', new_column_name='IFC')
    # [costPoint6] -> WeighmentDiff
    op.alter_column('CustomerEnquiryCosting', 'costPoint6', new_column_name='WeighmentDiff')
    # [costPoint7] -> CD
    op.alter_column('CustomerEnquiryCosting', 'costPoint7', new_column_name='CD')
    # [costPoint8] -> SWECharge
    op.alter_column('CustomerEnquiryCosting', 'costPoint8', new_column_name='SWECharge')
    # [costPoint9] -> CRS
    op.alter_column('CustomerEnquiryCosting', 'costPoint9', new_column_name='CRS')
    # [costPoint10] -> IncCharge
    op.alter_column('CustomerEnquiryCosting', 'costPoint10', new_column_name='IncCharge')
    # [costPoint11] -> ShortLnthCharge
    op.alter_column('CustomerEnquiryCosting', 'costPoint11', new_column_name='ShortLnthCharge')
    # [costPoint12] -> SpeciFicLnthCharge
    op.alter_column('CustomerEnquiryCosting', 'costPoint12', new_column_name='SpeciFicLnthCharge')
    # [costPoint13] -> ExtraCharge
    op.alter_column('CustomerEnquiryCosting', 'costPoint13', new_column_name='ExtraCharge')
    # [costPoint14] -> Fluctuation
    op.alter_column('CustomerEnquiryCosting', 'costPoint14', new_column_name='Fluctuation')
    # [costPoint15] -> Commission
    op.alter_column('CustomerEnquiryCosting', 'costPoint15', new_column_name='Commission')
    # [costPoint16] -> Misc
    op.alter_column('CustomerEnquiryCosting', 'costPoint16', new_column_name='Misc')
    # [costPoint17] -> Testing
    op.alter_column('CustomerEnquiryCosting', 'costPoint17', new_column_name='Testing')
    # [costPoint18] -> MOUTOD
    op.alter_column('CustomerEnquiryCosting', 'costPoint18', new_column_name='MOUTOD')
    # [costPoint19] -> SplDisc
    op.alter_column('CustomerEnquiryCosting', 'costPoint19', new_column_name='SplDisc')
    # [costPoint20] -> JC
    op.alter_column('CustomerEnquiryCosting', 'costPoint20', new_column_name='JC')


def downgrade() -> None:
    # Reverse column renames
    op.alter_column('CustomerEnquiryCosting', 'Marketing', new_column_name='TPWoGST')
    op.alter_column('CustomerEnquiryCosting', 'FreightTrailer', new_column_name='costPoint1')
    op.alter_column('CustomerEnquiryCosting', 'FreightTruck', new_column_name='costPoint2')
    op.alter_column('CustomerEnquiryCosting', 'Unloading', new_column_name='costPoint3')
    op.alter_column('CustomerEnquiryCosting', 'OHD', new_column_name='costPoint4')
    op.alter_column('CustomerEnquiryCosting', 'IFC', new_column_name='costPoint5')
    op.alter_column('CustomerEnquiryCosting', 'WeighmentDiff', new_column_name='costPoint6')
    op.alter_column('CustomerEnquiryCosting', 'CD', new_column_name='costPoint7')
    op.alter_column('CustomerEnquiryCosting', 'SWECharge', new_column_name='costPoint8')
    op.alter_column('CustomerEnquiryCosting', 'CRS', new_column_name='costPoint9')
    op.alter_column('CustomerEnquiryCosting', 'IncCharge', new_column_name='costPoint10')
    op.alter_column('CustomerEnquiryCosting', 'ShortLnthCharge', new_column_name='costPoint11')
    op.alter_column('CustomerEnquiryCosting', 'SpeciFicLnthCharge', new_column_name='costPoint12')
    op.alter_column('CustomerEnquiryCosting', 'ExtraCharge', new_column_name='costPoint13')
    op.alter_column('CustomerEnquiryCosting', 'Fluctuation', new_column_name='costPoint14')
    op.alter_column('CustomerEnquiryCosting', 'Commission', new_column_name='costPoint15')
    op.alter_column('CustomerEnquiryCosting', 'Misc', new_column_name='costPoint16')
    op.alter_column('CustomerEnquiryCosting', 'Testing', new_column_name='costPoint17')
    op.alter_column('CustomerEnquiryCosting', 'MOUTOD', new_column_name='costPoint18')
    op.alter_column('CustomerEnquiryCosting', 'SplDisc', new_column_name='costPoint19')
    op.alter_column('CustomerEnquiryCosting', 'JC', new_column_name='costPoint20')

    op.drop_column('UserMaster', 'userDesignation')

    op.drop_table('CommunicationLog')
    op.drop_table('CommunicationMode')
    op.drop_table('QuotQStatusMaster')
    op.drop_table('EnQStatusMaster')
