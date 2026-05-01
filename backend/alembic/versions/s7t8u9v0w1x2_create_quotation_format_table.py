"""Create QuotationFormat table

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-04-03 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "s7t8u9v0w1x2"
down_revision: Union[str, None] = "r6s7t8u9v0w1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "QuotationFormat",
        sa.Column("qfId", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("companyId", sa.Integer(), nullable=False),
        sa.Column("formatName", sa.String(200), nullable=False),
        sa.Column("qHeader", sa.Text(), nullable=True),
        sa.Column("qContent", sa.Text(), nullable=True),
        sa.Column("qFooter", sa.Text(), nullable=True),
        sa.Column("isCurrent", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("isActive", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("createdon", sa.DateTime(), nullable=True),
        sa.Column("createdby", sa.Integer(), nullable=True),
        sa.Column("lastupdateon", sa.DateTime(), nullable=True),
        sa.Column("lastupdateby", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["companyId"], ["Company.companyId"]),
        sa.PrimaryKeyConstraint("qfId"),
    )


def downgrade() -> None:
    op.drop_table("QuotationFormat")
