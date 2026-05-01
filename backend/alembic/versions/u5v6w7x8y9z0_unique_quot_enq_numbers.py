"""Unique(companyId, quotNo) and Unique(companyId, enqNo) filtered indexes

Prevents duplicate quotation/enquiry numbers within a tenant under concurrent
create. The backend already retries on IntegrityError; this constraint is the
DB-level safety net it relies on.

Filtered to `isActive = 1 AND <number> IS NOT NULL` so:
  - soft-deleted rows don't block reuse of a legitimately-freed number, and
  - unassigned rows (number NULL before save) don't collide with each other.

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-04-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "u5v6w7x8y9z0"
down_revision: Union[str, None] = "t4u5v6w7x8y9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "UX_QuotSummary_company_quotNo",
        "QuotSummary",
        ["companyId", "quotNo"],
        unique=True,
        mssql_where=sa.text("quotNo IS NOT NULL AND isActive = 1"),
    )
    op.create_index(
        "UX_CustomerEnquiry_company_enqNo",
        "CustomerEnquiry",
        ["companyId", "enqNo"],
        unique=True,
        mssql_where=sa.text("enqNo IS NOT NULL AND isActive = 1"),
    )


def downgrade() -> None:
    op.drop_index("UX_CustomerEnquiry_company_enqNo", table_name="CustomerEnquiry")
    op.drop_index("UX_QuotSummary_company_quotNo", table_name="QuotSummary")
