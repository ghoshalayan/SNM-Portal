"""Add print-styling columns to QuotationFormat

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8
Create Date: 2026-05-05 00:00:00.000000

Adds per-format print presentation overrides used by the quotation print
component (header colors, per-column alignment, decimal precision,
rounding mode, % suffix toggle). All columns are nullable so the print
component can fall back to hardcoded defaults if a value is NULL, but
``server_default`` backfills sensible values for every existing row so
the rendered output is consistent.

Factory defaults match the production look (blue header, white text)
plus the no-decimals + ceiling-rounding rule the user locked in.
``columnAlignments`` is left NULL on backfill — the print component
renders the baseline alignment map (numerics right, sequence/text
center) when null.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "w4x5y6z7a8b9"
down_revision: Union[str, None] = "v3w4x5y6z7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Header colors — accept any CSS color name or hex code; the print
    # component passes the value straight through to inline style.
    op.add_column(
        "QuotationFormat",
        sa.Column("headerBgColor", sa.String(50), nullable=True, server_default="#1565c0"),
    )
    op.add_column(
        "QuotationFormat",
        sa.Column("headerTextColor", sa.String(50), nullable=True, server_default="#FFFFFF"),
    )

    # Number formatting
    op.add_column(
        "QuotationFormat",
        sa.Column("roundingMode", sa.String(10), nullable=True, server_default="ceiling"),
    )
    op.add_column(
        "QuotationFormat",
        sa.Column("amountDecimals", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "QuotationFormat",
        sa.Column("taxDecimals", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "QuotationFormat",
        sa.Column("taxShowPercent", sa.Boolean(), nullable=True, server_default="0"),
    )
    op.add_column(
        "QuotationFormat",
        sa.Column("qtyDecimals", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "QuotationFormat",
        sa.Column("dimensionDecimals", sa.Integer(), nullable=True, server_default="0"),
    )

    # Per-column alignment JSON. Stored as plain text (NVARCHAR(MAX) on
    # SQL Server) — small enough that no separate index is warranted.
    # NULL on existing rows means "use baseline" in the print component.
    op.add_column(
        "QuotationFormat",
        sa.Column("columnAlignments", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("QuotationFormat", "columnAlignments")
    op.drop_column("QuotationFormat", "dimensionDecimals")
    op.drop_column("QuotationFormat", "qtyDecimals")
    op.drop_column("QuotationFormat", "taxShowPercent")
    op.drop_column("QuotationFormat", "taxDecimals")
    op.drop_column("QuotationFormat", "amountDecimals")
    op.drop_column("QuotationFormat", "roundingMode")
    op.drop_column("QuotationFormat", "headerTextColor")
    op.drop_column("QuotationFormat", "headerBgColor")
