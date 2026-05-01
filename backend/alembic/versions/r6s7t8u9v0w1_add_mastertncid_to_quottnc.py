"""Add masterTncId column to QuotTermsNConditions

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-04-03 14:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "r6s7t8u9v0w1"
down_revision: Union[str, None] = "q5r6s7t8u9v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "QuotTermsNConditions",
        sa.Column("masterTncId", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_quottnc_master_tncid",
        "QuotTermsNConditions",
        "TermsNConditionMaster",
        ["masterTncId"],
        ["tncId"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_quottnc_master_tncid", "QuotTermsNConditions", type_="foreignkey")
    op.drop_column("QuotTermsNConditions", "masterTncId")
