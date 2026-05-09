"""Phase 1.5: create QuotPOWorkingSheet — the Final Working Sheet entity.

The customer's PO can carry a different BOM (and different cost
heads) than the original quotation: qty deviation, late price
adjustments, etc. We promote the PO-level line items to their own
table so the quotation's Working Sheet (``QuotDetails``) stays the
canonical "what was quoted" record, while ``QuotPOWorkingSheet``
becomes "what was actually ordered" and feeds the downstream
viability + annexure generators.

Schema mirrors ``QuotDetails`` exactly so the existing line-items
grid component on the frontend can be reused — only the parent FK
(``quotPOId`` instead of ``quotId``) and the new ``sourceQuotDtlId``
audit pointer differ. Lines are mutable while
``QuotPurchaseOrder.status = 'Draft'`` and snapshotted on Submit &
Mature. Post-Submit edits go through the Unlock-and-Edit privileged
path, which creates a new PO version and clones the sheet to it.

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, None] = "s0t1u2v3w4x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "QuotPOWorkingSheet",
        sa.Column("poWorkingSheetId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "companyId", sa.Integer,
            sa.ForeignKey("Company.companyId"),
            nullable=False,
        ),
        sa.Column(
            "quotPOId", sa.Integer,
            sa.ForeignKey("QuotPurchaseOrder.quotPOId"),
            nullable=False,
        ),
        # Traceability back to the quoted line this row was cloned
        # from on Convert. Null for ad-hoc PO-only additions.
        sa.Column(
            "sourceQuotDtlId", sa.Integer,
            sa.ForeignKey("QuotDetails.quotDtlId"),
            nullable=True,
        ),

        # Identity (mirror QuotDetails)
        sa.Column("itemid", sa.Integer, sa.ForeignKey("ItemName.itemId"), nullable=True),
        sa.Column("itemName", sa.String(200), nullable=True),
        sa.Column("itemGradeName", sa.String(100), nullable=True),
        sa.Column("itemDia", sa.String(50), nullable=True),
        sa.Column("itemLength", sa.String(50), nullable=True),
        sa.Column("itemUnit", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 2), nullable=True),

        # Cost heads — same set + ordering as QuotDetails. Anything
        # added to QuotDetails later should also be added here so the
        # cloning service stays a straight column-by-column copy.
        sa.Column("TPWGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("Marketing", sa.Numeric(18, 2), nullable=True),
        sa.Column("FreightTrailer", sa.Numeric(18, 2), nullable=True),
        sa.Column("FreightTruck", sa.Numeric(18, 2), nullable=True),
        sa.Column("Unloading", sa.Numeric(18, 2), nullable=True),
        sa.Column("OHD", sa.Numeric(18, 2), nullable=True),
        sa.Column("IFC", sa.Numeric(18, 2), nullable=True),
        sa.Column("WeighmentDiff", sa.Numeric(18, 2), nullable=True),
        sa.Column("CD", sa.Numeric(18, 2), nullable=True),
        sa.Column("SWECharge", sa.Numeric(18, 2), nullable=True),
        sa.Column("CRS", sa.Numeric(18, 2), nullable=True),
        sa.Column("IncCharge", sa.Numeric(18, 2), nullable=True),
        sa.Column("ShortLnthCharge", sa.Numeric(18, 2), nullable=True),
        sa.Column("SpeciFicLnthCharge", sa.Numeric(18, 2), nullable=True),
        sa.Column("ExtraCharge", sa.Numeric(18, 2), nullable=True),
        sa.Column("Fluctuation", sa.Numeric(18, 2), nullable=True),
        sa.Column("Commission", sa.Numeric(18, 2), nullable=True),
        sa.Column("Misc", sa.Numeric(18, 2), nullable=True),
        sa.Column("Testing", sa.Numeric(18, 2), nullable=True),
        sa.Column("MOUTOD", sa.Numeric(18, 2), nullable=True),
        sa.Column("SplDisc", sa.Numeric(18, 2), nullable=True),
        sa.Column("JC", sa.Numeric(18, 2), nullable=True),

        sa.Column("modeOfDispatch", sa.String(200), nullable=True),

        # Calculated / GST
        sa.Column("basicRate", sa.Numeric(18, 2), nullable=True),
        sa.Column("totRate", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "gstMode", sa.String(20),
            nullable=True, server_default=sa.text("'IGST'"),
        ),
        sa.Column("IGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("CGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("SGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("totAmount", sa.Numeric(18, 2), nullable=True),

        # AuditMixin parity
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
    )

    # Common access pattern: list active lines for a PO.
    op.create_index(
        "IX_QuotPOWorkingSheet_quotPOId_active",
        "QuotPOWorkingSheet",
        ["quotPOId", "isActive"],
    )


def downgrade() -> None:
    op.drop_index(
        "IX_QuotPOWorkingSheet_quotPOId_active",
        table_name="QuotPOWorkingSheet",
    )
    op.drop_table("QuotPOWorkingSheet")
