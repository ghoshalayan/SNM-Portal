from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

from app.schemas.quot_purchase_order import QuotPurchaseOrderResponse


class QuotSummaryCreate(BaseModel):
    enqid: Optional[int] = None
    customerId: int
    customerContactId: Optional[int] = None
    siteId: Optional[int] = None
    quotNo: Optional[str] = None
    quotDate: Optional[date] = None
    subject: Optional[str] = None
    deliveryTermId: Optional[int] = None
    deliveryModeId: Optional[int] = None
    refQuotNo: Optional[str] = None
    remarks: Optional[str] = None
    codeUserId: Optional[int] = None  # for select_code mode

class QuotSummaryUpdate(QuotSummaryCreate):
    customerId: Optional[int] = None
    status: Optional[str] = None

class QuotSummaryResponse(BaseModel):
    quotId: int
    companyId: int
    ownerUserId: Optional[int] = None
    ownerRoleId: Optional[int] = None
    enqid: Optional[int] = None
    customerId: int
    customerContactId: Optional[int] = None
    siteId: Optional[int] = None
    quotNo: Optional[str] = None
    quotDate: Optional[date] = None
    subject: Optional[str] = None
    deliveryTermId: Optional[int] = None
    deliveryModeId: Optional[int] = None
    refQuotNo: Optional[str] = None
    remarks: Optional[str] = None
    revisionNo: Optional[int] = None
    versionNo: int
    parentQuotId: Optional[int] = None
    approvedby: Optional[int] = None
    approvedon: Optional[datetime] = None
    # Convert action audit pair (Phase 1) — set when the quotation
    # crosses the Approved → Converted forward gate.
    convertedOn: Optional[datetime] = None
    convertedBy: Optional[int] = None
    status: Optional[str] = None
    isActive: bool
    createdby: Optional[int] = None
    createdon: Optional[datetime] = None
    # Captured at the Approved → Converted transition. None for Draft /
    # Approved quotations that haven't crossed the gate yet.
    purchase_order: Optional[QuotPurchaseOrderResponse] = None
    class Config:
        from_attributes = True


class QuotSummaryListItem(QuotSummaryResponse):
    """Extended response for list endpoint with joined customer name."""
    customerName: Optional[str] = None
    class Config:
        from_attributes = True


class QuotDetailCreate(BaseModel):
    itemid: Optional[int] = None
    itemName: Optional[str] = None
    itemGradeName: Optional[str] = None
    itemDia: Optional[str] = None
    itemLength: Optional[str] = None
    itemUnit: Optional[str] = None
    quantity: Optional[float] = None
    # Cost heads
    TPWGST: Optional[float] = None
    Marketing: Optional[float] = None
    FreightTrailer: Optional[float] = None
    FreightTruck: Optional[float] = None
    Unloading: Optional[float] = None
    OHD: Optional[float] = None
    IFC: Optional[float] = None
    WeighmentDiff: Optional[float] = None
    CD: Optional[float] = None
    SWECharge: Optional[float] = None
    CRS: Optional[float] = None
    IncCharge: Optional[float] = None
    ShortLnthCharge: Optional[float] = None
    SpeciFicLnthCharge: Optional[float] = None
    ExtraCharge: Optional[float] = None
    Fluctuation: Optional[float] = None
    Commission: Optional[float] = None
    Misc: Optional[float] = None
    Testing: Optional[float] = None
    MOUTOD: Optional[float] = None
    SplDisc: Optional[float] = None
    JC: Optional[float] = None
    modeOfDispatch: Optional[str] = None
    # Calculated
    basicRate: Optional[float] = None
    totRate: Optional[float] = None
    gstMode: Optional[str] = "IGST"
    IGST: Optional[float] = None
    CGST: Optional[float] = None
    SGST: Optional[float] = None
    totAmount: Optional[float] = None

class QuotDetailResponse(QuotDetailCreate):
    quotDtlId: int
    quotId: int
    companyId: int
    isActive: bool
    class Config:
        from_attributes = True


class QuotTncCreate(BaseModel):
    masterTncId: Optional[int] = None
    tncName: Optional[str] = None
    tncDescription: Optional[str] = None
    sortOrder: Optional[int] = 0

class QuotTncResponse(QuotTncCreate):
    quotTncId: int
    quotId: int
    companyId: int
    masterTncId: Optional[int] = None
    sortOrder: int
    isActive: bool
    class Config:
        from_attributes = True


class QuotTncReorderItem(BaseModel):
    quotTncId: int
    sortOrder: int


# --- Quotation Follow-Up ---
class QuotFollowUpCreate(BaseModel):
    followupdate: Optional[date] = None
    followupremarks: Optional[str] = None
    followupmode: Optional[str] = None
    nextfollowupdate: Optional[date] = None


class QuotFollowUpResponse(QuotFollowUpCreate):
    quotfollowupid: int
    quotId: int
    createdon: Optional[datetime] = None
    createdby: Optional[int] = None
    isActive: bool
    class Config:
        from_attributes = True
