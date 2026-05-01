"""Add CanApproveAnnexure flag to RoleMenuMap

Annexure approval is being separated from regular quotation approval —
only roles with this flag (e.g. the new "Commercial HOD" template) can
approve quotation annexures and edit them after they've been approved.
Regular HODs keep CanApprove for quotation-level approval but lose
annexure approval rights.

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "l3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable=False with a server_default so existing rows get a
    # concrete 0 written by SQL Server, then drop the default once the
    # backfill is complete (model declares its own Python-side default
    # of False for new inserts).
    op.add_column(
        "RoleMenuMap",
        sa.Column(
            "CanApproveAnnexure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.alter_column("RoleMenuMap", "CanApproveAnnexure", server_default=None)


def downgrade() -> None:
    op.drop_column("RoleMenuMap", "CanApproveAnnexure")
