from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# Print styling fields are optional on Create/Update — the migration
# backfills sensible defaults at the DB level, so callers that don't
# care about styling can omit them entirely.
_PRINT_STYLE_FIELDS = """
    headerBgColor: Optional[str]      -- e.g. "#1565c0" or any CSS color name
    headerTextColor: Optional[str]
    roundingMode: Optional[str]       -- "ceiling" | "floor" | "round"
    amountDecimals: Optional[int]     -- 0-2
    taxDecimals: Optional[int]        -- 0-2
    taxShowPercent: Optional[bool]
    qtyDecimals: Optional[int]        -- 0-3
    dimensionDecimals: Optional[int]  -- 0-1
    columnAlignments: Optional[str]   -- JSON: { col: { header, body } }
"""


class QuotationFormatCreate(BaseModel):
    formatName: str
    qHeader: Optional[str] = None
    qContent: Optional[str] = None
    qFooter: Optional[str] = None
    isCurrent: bool = False
    # Print styling
    headerBgColor: Optional[str] = None
    headerTextColor: Optional[str] = None
    roundingMode: Optional[str] = None
    amountDecimals: Optional[int] = None
    taxDecimals: Optional[int] = None
    taxShowPercent: Optional[bool] = None
    qtyDecimals: Optional[int] = None
    dimensionDecimals: Optional[int] = None
    columnAlignments: Optional[str] = None


class QuotationFormatUpdate(BaseModel):
    formatName: Optional[str] = None
    qHeader: Optional[str] = None
    qContent: Optional[str] = None
    qFooter: Optional[str] = None
    isCurrent: Optional[bool] = None
    # Print styling
    headerBgColor: Optional[str] = None
    headerTextColor: Optional[str] = None
    roundingMode: Optional[str] = None
    amountDecimals: Optional[int] = None
    taxDecimals: Optional[int] = None
    taxShowPercent: Optional[bool] = None
    qtyDecimals: Optional[int] = None
    dimensionDecimals: Optional[int] = None
    columnAlignments: Optional[str] = None


class QuotationFormatResponse(BaseModel):
    qfId: int
    companyId: int
    formatName: str
    qHeader: Optional[str] = None
    qContent: Optional[str] = None
    qFooter: Optional[str] = None
    isCurrent: bool
    isActive: bool
    createdon: Optional[datetime] = None
    # Print styling
    headerBgColor: Optional[str] = None
    headerTextColor: Optional[str] = None
    roundingMode: Optional[str] = None
    amountDecimals: Optional[int] = None
    taxDecimals: Optional[int] = None
    taxShowPercent: Optional[bool] = None
    qtyDecimals: Optional[int] = None
    dimensionDecimals: Optional[int] = None
    columnAlignments: Optional[str] = None

    class Config:
        from_attributes = True


class QuotationFormatListItem(BaseModel):
    """Lightweight response for list endpoint — excludes HTML blobs."""
    qfId: int
    companyId: int
    formatName: str
    isCurrent: bool
    isActive: bool
    createdon: Optional[datetime] = None

    class Config:
        from_attributes = True
