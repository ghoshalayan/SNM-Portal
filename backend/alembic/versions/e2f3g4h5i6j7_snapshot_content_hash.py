"""Add ``contentHash`` to viability + annexure approval snapshots.

Brings these two snapshot tables to parity with ``QuotFWSApprovalSnapshot``
so the D3 short-circuit ("no content change since last Approve →
audit-only event, no new snapshot row") can be applied uniformly across
all three soft-flow entities.

Backwards-compatibility: existing snapshot rows predate this column and
get NULL. The service-layer D3 check treats NULL as "no comparable
hash" and falls through to writing a fresh snapshot — slightly noisier
than the strict no-op path but never wrong.

Revision ID: e2f3g4h5i6j7
Revises: d1e2f3g4h5i6
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3g4h5i6j7"
down_revision: Union[str, None] = "d1e2f3g4h5i6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Viability snapshots
    op.add_column(
        "QuotViabilityApprovalSnapshot",
        sa.Column("contentHash", sa.String(length=64), nullable=True),
    )
    # Annexure snapshots
    op.add_column(
        "QuotAnnexureApprovalSnapshot",
        sa.Column("contentHash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("QuotAnnexureApprovalSnapshot", "contentHash")
    op.drop_column("QuotViabilityApprovalSnapshot", "contentHash")
