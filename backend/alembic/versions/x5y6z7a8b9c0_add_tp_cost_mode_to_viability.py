"""Add tpCostMode + tpCostAsOfDate to QuotViabilitySheet

Revision ID: x5y6z7a8b9c0
Revises: w4x5y6z7a8b9
Create Date: 2026-05-17 00:00:00.000000

Adds the TP-Cost sourcing toggle to the Viability Sheet (CR — Selected
Datewise / Quot Approval Dated). ``tpCostMode`` is the picked mode and
``tpCostAsOfDate`` is the date the user picked when mode is
``'as_of_date'`` — NULL means "today".

Legacy rows are backfilled to ``'as_of_date'`` with a NULL date so the
sheet renders today's rate, matching the pre-CR behaviour.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "x5y6z7a8b9c0"
down_revision: Union[str, None] = "w4x5y6z7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "QuotViabilitySheet",
        sa.Column(
            "tpCostMode", sa.String(20), nullable=True,
            server_default="as_of_date",
        ),
    )
    op.add_column(
        "QuotViabilitySheet",
        sa.Column("tpCostAsOfDate", sa.Date(), nullable=True),
    )
    # Legacy rows: stamp mode so the frontend toggle has a value to bind.
    # tpCostAsOfDate stays NULL (= today) to match pre-CR rendering.
    op.execute(
        "UPDATE QuotViabilitySheet SET tpCostMode = 'as_of_date' "
        "WHERE tpCostMode IS NULL"
    )


def downgrade() -> None:
    op.drop_column("QuotViabilitySheet", "tpCostAsOfDate")
    op.drop_column("QuotViabilitySheet", "tpCostMode")
