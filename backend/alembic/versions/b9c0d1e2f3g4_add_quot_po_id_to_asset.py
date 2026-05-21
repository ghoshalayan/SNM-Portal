"""Add quotPOId to Asset for per-PO/LOI attachment scoping.

Phase 1H follow-up (Issue #1/#2 — per-PO picker on PO Header tab):
the asset upload now optionally writes ``quotPOId`` so attachments
hang off a specific PO/LOI row inside a cycle. Nullable — legacy
quotation-scoped uploads (``quotId`` set, ``quotPOId`` NULL) keep
working unchanged.

Revision ID: b9c0d1e2f3g4
Revises: a8b9c0d1e2f3
Create Date: 2026-05-19 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c0d1e2f3g4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "Asset",
        sa.Column("quotPOId", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "FK_Asset_quotPOId",
        source_table="Asset",
        referent_table="QuotPurchaseOrder",
        local_cols=["quotPOId"],
        remote_cols=["quotPOId"],
    )


def downgrade() -> None:
    op.drop_constraint("FK_Asset_quotPOId", "Asset", type_="foreignkey")
    op.drop_column("Asset", "quotPOId")
