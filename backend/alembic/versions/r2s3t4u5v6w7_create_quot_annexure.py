"""Create QuotAnnexure

Final post-viability stage: a structured document attached to each matured
quotation. Most fields auto-populate from the quotation + customer + viability
data at generation time; a handful are pure KRO/HOD input.

Single annexure per quotation (UNIQUE active row on quotId).

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-04-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "r2s3t4u5v6w7"
down_revision: Union[str, None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "QuotAnnexure",
        sa.Column("annexureId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("quotId", sa.Integer, sa.ForeignKey("QuotSummary.quotId"), nullable=False),
        sa.Column("viabilityId", sa.Integer, sa.ForeignKey("QuotViabilitySheet.viabilityId"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="Draft"),

        # --- Header block (top of the document) ---
        sa.Column("clientName", sa.String(500), nullable=True),
        sa.Column("customerPONo", sa.String(50), nullable=True),
        sa.Column("customerPODate", sa.Date, nullable=True),
        sa.Column("totalBillableAmount", sa.Numeric(18, 2), nullable=True),
        sa.Column("totalQuantityMT", sa.Numeric(18, 2), nullable=True),

        # --- 25 body fields ---
        sa.Column("invoicing", sa.String(200), nullable=True, server_default="Manufacturing"),
        sa.Column("transportationMode", sa.String(50), nullable=True),      # Trailer / Truck
        sa.Column("tcType", sa.String(50), nullable=True),                  # Low Alloy TC / Normal TC
        sa.Column("paymentTerms", sa.Text, nullable=True),
        sa.Column("loadabilityQty", sa.Numeric(18, 2), nullable=True),
        sa.Column("transportChargesPerMT", sa.Numeric(18, 2), nullable=True),
        sa.Column("transportChargesFOR", sa.String(500), nullable=True),
        sa.Column("specificLength", sa.String(200), nullable=True),
        sa.Column("tolerance", sa.String(200), nullable=True, server_default="No excess delivery"),
        sa.Column("deliverySchedule", sa.Text, nullable=True),
        sa.Column("transportRealizationPerMT", sa.Numeric(18, 2), nullable=True),
        sa.Column("panNo", sa.String(50), nullable=True),
        sa.Column("gstNo", sa.String(50), nullable=True),
        sa.Column("contactPerson", sa.String(200), nullable=True),
        sa.Column("contactPersonNumber", sa.String(50), nullable=True),
        sa.Column("billingAddress", sa.Text, nullable=True),
        sa.Column("consigneeAddress", sa.Text, nullable=True),
        sa.Column("qualityFe", sa.String(50), nullable=True),               # Fe-500D / Fe-550D
        sa.Column("qualityStandard", sa.String(50), nullable=True, server_default="IS-1786"),
        sa.Column("qualityStandardLength", sa.String(200), nullable=True),
        sa.Column("companyName", sa.String(100), nullable=True, server_default="DGP"),
        sa.Column("billsTo", sa.String(50), nullable=True, server_default="HO"),  # SITE / HO
        sa.Column("totalOutstanding", sa.Numeric(18, 2), nullable=True),
        sa.Column("overdueOutstanding", sa.Numeric(18, 2), nullable=True),
        sa.Column("diawiseBreakup", sa.Text, nullable=True),                # JSON serialized
        sa.Column("unloadingScope", sa.String(50), nullable=True),          # CUSTOMER / SRMB
        sa.Column("unloadingRate", sa.Numeric(18, 2), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),

        # --- Signatures ---
        sa.Column("preparedByUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("preparedByName", sa.String(200), nullable=True),
        sa.Column("checkedByUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("checkedByName", sa.String(200), nullable=True),
        sa.Column("approvedByUserId", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("approvedByName", sa.String(200), nullable=True),
        sa.Column("approvedon", sa.DateTime, nullable=True),

        # --- Audit ---
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
    )

    # Single-annexure-per-quotation rule (among active rows).
    op.create_index(
        "UX_QuotAnnexure_quotId_active",
        "QuotAnnexure",
        ["quotId"],
        unique=True,
        mssql_where=sa.text("isActive = 1"),
    )


def downgrade() -> None:
    op.drop_index("UX_QuotAnnexure_quotId_active", table_name="QuotAnnexure")
    op.drop_table("QuotAnnexure")
