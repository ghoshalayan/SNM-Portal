"""Create QuotPurchaseOrder + add CustomerSite.isAdHoc + drop CustomerPONo/Date.

The customer Purchase Order graduates from two scalar columns on
``QuotSummary`` (``CustomerPONo`` / ``CustomerPODate``) to a real entity:

  - ``QuotPurchaseOrder`` is 1:1 with ``QuotSummary`` (enforced via a
    filtered unique index on ``quotId`` for active rows). Capturing this
    row IS the Approved → Matured transition.
  - ``CustomerSite.isAdHoc`` flags one-off sites created via the PO's
    "save manually entered address permanently" flow so they don't
    pollute the regular site picker.

Existing data (quotations that already have a ``CustomerPONo`` set,
typically the ones already in ``Matured``+ status) is backfilled into the
new table before the source columns are dropped, so the annexure
generator's switch from ``quotation.customerContactId``/``siteId`` to
``po.contact``/``po.billing_site``/``po.consignee_site`` keeps working
for historic data.

Revision ID: p7q8r9s0t1u2
Revises: o6p7q8r9s0t1
Create Date: 2026-05-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "p7q8r9s0t1u2"
down_revision: Union[str, None] = "o6p7q8r9s0t1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) New PO entity.
    op.create_table(
        "QuotPurchaseOrder",
        sa.Column("quotPOId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("quotId", sa.Integer, sa.ForeignKey("QuotSummary.quotId"), nullable=False),

        sa.Column("poNo", sa.String(50), nullable=False),
        sa.Column("poDate", sa.Date, nullable=False),

        sa.Column(
            "customerId",
            sa.Integer,
            sa.ForeignKey("CustomerMaster.customerId"),
            nullable=False,
        ),
        sa.Column(
            "customerContactId",
            sa.Integer,
            sa.ForeignKey("CustomerContacts.customerContactId"),
            nullable=True,
        ),

        sa.Column(
            "billingSiteId",
            sa.Integer,
            sa.ForeignKey("CustomerSite.siteId"),
            nullable=True,
        ),
        sa.Column("billingAddressManual", sa.String(500), nullable=True),
        sa.Column(
            "consigneeSiteId",
            sa.Integer,
            sa.ForeignKey("CustomerSite.siteId"),
            nullable=True,
        ),
        sa.Column("consigneeAddressManual", sa.String(500), nullable=True),

        sa.Column("remarks", sa.String(500), nullable=True),

        # AuditMixin
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
    )

    # 1:1 in v1 — filtered unique index so soft-deleted rows don't block
    # a re-capture. Mirrors the QuotAnnexure pattern (see
    # ``r2s3t4u5v6w7_create_quot_annexure.py``).
    op.create_index(
        "UX_QuotPurchaseOrder_quotId_active",
        "QuotPurchaseOrder",
        ["quotId"],
        unique=True,
        mssql_where=sa.text("isActive = 1"),
    )

    # 2) ``isAdHoc`` flag on CustomerSite. server_default=0 backfills
    # existing rows; we then clear the default so future inserts must
    # provide an explicit value (matches the rest of the codebase).
    op.add_column(
        "CustomerSite",
        sa.Column(
            "isAdHoc",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.alter_column("CustomerSite", "isAdHoc", server_default=None)

    # 3) Backfill the new table from any QuotSummary that already had
    # PO data. Best-effort defaults for the new override fields:
    #   - customerId / customerContactId  → quotation's
    #   - billingSiteId / consigneeSiteId → quotation.siteId (pre-PO
    #     world had only one site, so seeding both with it is the
    #     least-surprising default; the user can edit afterwards).
    op.execute(
        """
        INSERT INTO QuotPurchaseOrder (
            companyId, quotId, poNo, poDate,
            customerId, customerContactId,
            billingSiteId, billingAddressManual,
            consigneeSiteId, consigneeAddressManual,
            isActive, createdon, createdby
        )
        SELECT
            q.companyId, q.quotId, q.CustomerPONo, q.CustomerPODate,
            q.customerId, q.customerContactId,
            q.siteId, NULL,
            q.siteId, NULL,
            1, q.createdon, q.createdby
        FROM QuotSummary q
        WHERE q.CustomerPONo IS NOT NULL
          AND LTRIM(RTRIM(q.CustomerPONo)) <> ''
          AND q.CustomerPODate IS NOT NULL
        """
    )

    # 4) Now safe to drop the source columns.
    op.drop_column("QuotSummary", "CustomerPONo")
    op.drop_column("QuotSummary", "CustomerPODate")


def downgrade() -> None:
    # Re-add the source columns nullable so the back-copy can run.
    op.add_column("QuotSummary", sa.Column("CustomerPONo", sa.String(50), nullable=True))
    op.add_column("QuotSummary", sa.Column("CustomerPODate", sa.Date(), nullable=True))

    # Copy poNo/poDate back so a roll-back doesn't lose the user's data.
    op.execute(
        """
        UPDATE q
        SET q.CustomerPONo = po.poNo,
            q.CustomerPODate = po.poDate
        FROM QuotSummary q
        INNER JOIN QuotPurchaseOrder po ON po.quotId = q.quotId
        WHERE po.isActive = 1
        """
    )

    op.drop_index("UX_QuotPurchaseOrder_quotId_active", table_name="QuotPurchaseOrder")
    op.drop_table("QuotPurchaseOrder")
    op.drop_column("CustomerSite", "isAdHoc")
