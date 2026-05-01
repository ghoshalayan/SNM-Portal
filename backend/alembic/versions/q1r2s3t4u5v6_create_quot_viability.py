"""Create QuotViabilitySheet and QuotViabilityLine

Introduces the Viability Sheet stage that follows a Matured quotation.
Viability lives in its own tables so the matured quotation snapshot stays
immutable; edits here never mutate QuotDetails.

Single sheet per quotation (enforced via UNIQUE on quotId).

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-04-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, None] = "p0q1r2s3t4u5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COST_HEAD_COLS = [
    "TPWGST", "Marketing", "FreightTrailer", "FreightTruck", "Unloading",
    "OHD", "IFC", "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge",
    "ShortLnthCharge", "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
    "Commission", "Misc", "Testing", "MOUTOD", "SplDisc", "JC",
]


def upgrade() -> None:
    # Header table — one row per (quotId). isActive from AuditMixin-style.
    op.create_table(
        "QuotViabilitySheet",
        sa.Column("viabilityId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("quotId", sa.Integer, sa.ForeignKey("QuotSummary.quotId"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Draft"),
        sa.Column("approvedby", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("approvedon", sa.DateTime, nullable=True),
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
    )
    # Single-sheet-per-quotation rule (among active rows).
    op.create_index(
        "UX_QuotViabilitySheet_quotId_active",
        "QuotViabilitySheet",
        ["quotId"],
        unique=True,
        mssql_where=sa.text("isActive = 1"),
    )

    # Lines table — full snapshot of QuotDetails + goal-seek + gross columns.
    line_cols = [
        sa.Column("viabilityLineId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("viabilityId", sa.Integer, sa.ForeignKey("QuotViabilitySheet.viabilityId"), nullable=False),
        sa.Column("sourceQuotDtlId", sa.Integer, sa.ForeignKey("QuotDetails.quotDtlId"), nullable=True),
        # Identity / grouping
        sa.Column("itemid", sa.Integer, sa.ForeignKey("ItemName.itemId"), nullable=True),
        sa.Column("itemName", sa.String(200), nullable=True),
        sa.Column("itemGradeName", sa.String(100), nullable=True),
        sa.Column("itemDia", sa.String(50), nullable=True),
        sa.Column("itemLength", sa.String(50), nullable=True),
        sa.Column("itemUnit", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 2), nullable=True),
        sa.Column("orderedQty", sa.Numeric(18, 2), nullable=True),
        sa.Column("modeOfDispatch", sa.String(200), nullable=True),
    ]
    # All 22 cost heads (TPWGST + 21 adjustable)
    line_cols += [sa.Column(c, sa.Numeric(18, 2), nullable=True) for c in COST_HEAD_COLS]
    # Calculated + GST
    line_cols += [
        sa.Column("basicRate", sa.Numeric(18, 2), nullable=True),
        sa.Column("totRate", sa.Numeric(18, 2), nullable=True),
        sa.Column("gstMode", sa.String(20), nullable=True, server_default="IGST"),
        sa.Column("IGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("CGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("SGST", sa.Numeric(18, 2), nullable=True),
        sa.Column("totAmount", sa.Numeric(18, 2), nullable=True),          # EX/FOR Price per MT (incl GST)
        # Gross columns (per-line)
        sa.Column("totalAmount", sa.Numeric(18, 2), nullable=True),        # totRate * orderedQty
        sa.Column("totalGst", sa.Numeric(18, 2), nullable=True),           # GST * orderedQty
        sa.Column("grossExForPrice", sa.Numeric(18, 2), nullable=True),    # totAmount * orderedQty
        # Goal-seek trail
        sa.Column("targetTotRate", sa.Numeric(18, 2), nullable=True),
        sa.Column("adjustableHeads", sa.String(500), nullable=True),
        # Audit
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
    ]
    op.create_table("QuotViabilityLine", *line_cols)

    op.create_index(
        "IX_QuotViabilityLine_viabilityId",
        "QuotViabilityLine",
        ["viabilityId", "isActive"],
    )


def downgrade() -> None:
    op.drop_index("IX_QuotViabilityLine_viabilityId", table_name="QuotViabilityLine")
    op.drop_table("QuotViabilityLine")
    op.drop_index("UX_QuotViabilitySheet_quotId_active", table_name="QuotViabilitySheet")
    op.drop_table("QuotViabilitySheet")
