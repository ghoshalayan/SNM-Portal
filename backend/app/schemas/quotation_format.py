from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class QuotationFormatCreate(BaseModel):
    formatName: str
    qHeader: Optional[str] = None
    qContent: Optional[str] = None
    qFooter: Optional[str] = None
    isCurrent: bool = False


class QuotationFormatUpdate(BaseModel):
    formatName: Optional[str] = None
    qHeader: Optional[str] = None
    qContent: Optional[str] = None
    qFooter: Optional[str] = None
    isCurrent: Optional[bool] = None


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
