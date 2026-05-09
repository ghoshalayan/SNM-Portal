"""Phase 3: source-version pointers on downstream lifecycle entities.

Stamp columns that record which upstream version each downstream
entity was sourced from. The frontend uses these to detect "stale"
state — a downstream stage shows a banner + Re-source action when
its stamped source version is older than the current upstream head.

* ``QuotPurchaseOrder.sourcedFromQuotationVersion`` — the
  ``QuotSummary.versionNo`` that was active when this PO was
  Converted. Bumps when the PO is re-sourced after the quotation is
  Revised.
* ``QuotViabilitySheet.sourcedFromPOVersion`` — the
  ``QuotPurchaseOrder.versionNo`` whose Final Working Sheet was the
  source for this viability sheet.
* ``QuotAnnexure.sourcedFromQuotationVersion`` /
  ``sourcedFromPOVersion`` / ``sourcedFromViabilityVersion`` —
  three pointers since the annexure auto-fills from all three.

All columns are nullable. Existing rows get a best-effort backfill
from the matching upstream's current ``versionNo`` so legacy rows
don't show as "stale" for no reason.

Revision ID: u2v3w4x5y6z7
Revises: t1u2v3w4x5y6
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column("sourcedFromQuotationVersion", sa.Integer, nullable=True),
    )
    op.add_column(
        "QuotViabilitySheet",
        sa.Column("sourcedFromPOVersion", sa.Integer, nullable=True),
    )
    op.add_column(
        "QuotAnnexure",
        sa.Column("sourcedFromQuotationVersion", sa.Integer, nullable=True),
    )
    op.add_column(
        "QuotAnnexure",
        sa.Column("sourcedFromPOVersion", sa.Integer, nullable=True),
    )
    op.add_column(
        "QuotAnnexure",
        sa.Column("sourcedFromViabilityVersion", sa.Integer, nullable=True),
    )

    # Best-effort backfill: match each downstream row to its parent
    # quotation / PO / viability and copy their current versionNo.
    # Legacy rows therefore look "fresh" rather than stale at the
    # moment Phase 3 lands; future upstream Revises will bump pointers
    # via the new stamp logic.
    op.execute("""
        UPDATE po
        SET po.sourcedFromQuotationVersion = q.versionNo
        FROM QuotPurchaseOrder po
        INNER JOIN QuotSummary q ON q.quotId = po.quotId
        WHERE po.sourcedFromQuotationVersion IS NULL
    """)
    op.execute("""
        UPDATE v
        SET v.sourcedFromPOVersion = po.versionNo
        FROM QuotViabilitySheet v
        INNER JOIN QuotPurchaseOrder po ON po.quotId = v.quotId AND po.isActive = 1
        WHERE v.sourcedFromPOVersion IS NULL
    """)
    op.execute("""
        UPDATE a
        SET a.sourcedFromQuotationVersion = q.versionNo
        FROM QuotAnnexure a
        INNER JOIN QuotSummary q ON q.quotId = a.quotId
        WHERE a.sourcedFromQuotationVersion IS NULL
    """)
    op.execute("""
        UPDATE a
        SET a.sourcedFromPOVersion = po.versionNo
        FROM QuotAnnexure a
        INNER JOIN QuotPurchaseOrder po ON po.quotId = a.quotId AND po.isActive = 1
        WHERE a.sourcedFromPOVersion IS NULL
    """)
    op.execute("""
        UPDATE a
        SET a.sourcedFromViabilityVersion = v.versionNo
        FROM QuotAnnexure a
        INNER JOIN QuotViabilitySheet v
          ON v.viabilityId = a.viabilityId
        WHERE a.sourcedFromViabilityVersion IS NULL
    """)


def downgrade() -> None:
    op.drop_column("QuotAnnexure", "sourcedFromViabilityVersion")
    op.drop_column("QuotAnnexure", "sourcedFromPOVersion")
    op.drop_column("QuotAnnexure", "sourcedFromQuotationVersion")
    op.drop_column("QuotViabilitySheet", "sourcedFromPOVersion")
    op.drop_column("QuotPurchaseOrder", "sourcedFromQuotationVersion")
