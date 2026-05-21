"""Rename tpCostMode 'approved_date' -> 'po_working_sheet'

Revision ID: y6z7a8b9c0d1
Revises: x5y6z7a8b9c0
Create Date: 2026-05-17 12:00:00.000000

The second TP-Cost mode was originally labeled "Quot Approval Dated"
and looked up the rate-table at the quotation's approval date. The
user clarified the intent is different: use the TPWGST that was
actually frozen on the Final Working Sheet when the PO was captured.

The semantics live in code (viability_service.refresh_sheet_tp_cost);
this migration just renames any dev-test rows whose tpCostMode is
the now-defunct 'approved_date' so they don't fail Pydantic
``Literal["as_of_date", "po_working_sheet"]`` validation on read.

Safe to run even when no rows match — UPDATE returns 0.
"""
from typing import Sequence, Union
from alembic import op


revision: str = "y6z7a8b9c0d1"
down_revision: Union[str, None] = "x5y6z7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE QuotViabilitySheet "
        "SET tpCostMode = 'po_working_sheet' "
        "WHERE tpCostMode = 'approved_date'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE QuotViabilitySheet "
        "SET tpCostMode = 'approved_date' "
        "WHERE tpCostMode = 'po_working_sheet'"
    )
