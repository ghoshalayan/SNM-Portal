"""create CustomerEnqFollowUp table

Revision ID: u9v0w1x2y3z4
Revises: t8u9v0w1x2y3
Create Date: 2026-04-04

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "u9v0w1x2y3z4"
down_revision: Union[str, None] = "t8u9v0w1x2y3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "CustomerEnqFollowUp",
        sa.Column("engfollowupid", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("enqid", sa.Integer, sa.ForeignKey("CustomerEnquiry.enqid"), nullable=False),
        sa.Column("followupdate", sa.Date, nullable=True),
        sa.Column("followupremarks", sa.String(500), nullable=True),
        sa.Column("followupmode", sa.String(50), nullable=True),
        sa.Column("nextfollowupdate", sa.Date, nullable=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
        sa.Column("isActive", sa.Boolean, server_default=sa.text("1"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("CustomerEnqFollowUp")
