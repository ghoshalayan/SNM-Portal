"""Add ``fwsStatus`` to QuotOrderCycle for lock-after-approve lifecycle.

Final Working Sheet gets the same Draft/Approved discipline that
Viability and Annexure already have on their ``status`` columns. The
cycle's own ``status`` (Active / Complete / Abandoned) stays for the
call-off-level lifecycle; the new ``fwsStatus`` carries the FWS-level
state independently:

  * ``draft``    — live FWS rows are editable; line CRUD is allowed.
  * ``approved`` — content matches the latest snapshot; line CRUD is
                   rejected with 409. Re-generate flips this back to
                   ``draft`` (creating a new editable working set).

Default for both new and existing rows is ``draft``. The 2026-05-21
soft-flow UX rework standardised on Draft→Approve→Approved→Re-generate
across all three stages; this migration is the data-model half for
FWS.

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-05-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3g4h5i6j7k8"
down_revision: Union[str, None] = "e2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "QuotOrderCycle",
        sa.Column(
            "fwsStatus",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
    )


def downgrade() -> None:
    op.drop_column("QuotOrderCycle", "fwsStatus")
