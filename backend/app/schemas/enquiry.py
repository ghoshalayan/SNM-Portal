from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


class EnquiryCreate(BaseModel):
    customerId: int
    customerContactId: Optional[int] = None
    siteId: Optional[int] = None
    enqNo: Optional[str] = None
    enqDate: Optional[date] = None
    enqMode: Optional[str] = None
    description: Optional[str] = None
    validityDays: Optional[int] = None
    codeUserId: Optional[int] = None  # for select_code mode

class EnquiryUpdate(EnquiryCreate):
    customerId: Optional[int] = None
    status: Optional[str] = None

class EnquiryResponse(BaseModel):
    enqid: int
    companyId: int
    ownerUserId: Optional[int] = None
    ownerRoleId: Optional[int] = None
    customerId: int
    customerContactId: Optional[int] = None
    siteId: Optional[int] = None
    enqNo: Optional[str] = None
    enqDate: Optional[date] = None
    enqMode: Optional[str] = None
    description: Optional[str] = None
    validityDays: Optional[int] = None
    status: Optional[str] = None
    isActive: bool
    createdby: Optional[int] = None
    createdon: Optional[datetime] = None
    class Config:
        from_attributes = True


class EnquiryDetailCreate(BaseModel):
    itemid: Optional[int] = None
    itemGradeName: Optional[str] = None
    itemDia: Optional[str] = None
    itemLength: Optional[str] = None
    itemUnit: Optional[str] = None
    quantity: Optional[float] = None
    remarks: Optional[str] = None

class EnquiryDetailResponse(BaseModel):
    enqdtlid: int
    enqid: int
    itemid: Optional[int] = None
    itemGradeName: Optional[str] = None
    itemDia: Optional[str] = None
    itemLength: Optional[str] = None
    itemUnit: Optional[str] = None
    quantity: Optional[float] = None
    remarks: Optional[str] = None
    isActive: bool
    class Config:
        from_attributes = True


class EnquiryCostingCreate(BaseModel):
    enqdtlid: int
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
    basicRate: Optional[float] = None
    GST: Optional[float] = None
    EXFORPrice: Optional[float] = None

class EnquiryCostingResponse(EnquiryCostingCreate):
    enqCostingId: int
    enqid: int
    versionNo: int
    isActive: bool
    class Config:
        from_attributes = True


# --- Enquiry Follow-Up ---
class FollowUpCreate(BaseModel):
    followupdate: Optional[date] = None
    followupremarks: Optional[str] = None
    followupmode: Optional[str] = None
    nextfollowupdate: Optional[date] = None

class FollowUpResponse(FollowUpCreate):
    engfollowupid: int
    enqid: int
    createdon: Optional[datetime] = None
    createdby: Optional[int] = None
    isActive: bool
    class Config:
        from_attributes = True
