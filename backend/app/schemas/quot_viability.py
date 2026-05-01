from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


# The 21 adjustable cost heads (Marketing → JC). TPWGST is the base and is
# only changed via the dia-refresh path, never by goal-seek.
ADJUSTABLE_HEADS: List[str] = [
    "Marketing", "FreightTrailer", "FreightTruck", "Unloading", "OHD", "IFC",
    "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge", "ShortLnthCharge",
    "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation", "Commission", "Misc",
    "Testing", "MOUTOD", "SplDisc", "JC",
]


class ViabilityLineResponse(BaseModel):
    viabilityLineId: int
    viabilityId: int
    sourceQuotDtlId: Optional[int] = None

    itemid: Optional[int] = None
    itemName: Optional[str] = None
    itemGradeName: Optional[str] = None
    itemDia: Optional[str] = None
    itemLength: Optional[str] = None
    itemUnit: Optional[str] = None
    quantity: Optional[Decimal] = None
    orderedQty: Optional[Decimal] = None
    modeOfDispatch: Optional[str] = None

    # Cost heads
    TPWGST: Optional[Decimal] = None
    Marketing: Optional[Decimal] = None
    FreightTrailer: Optional[Decimal] = None
    FreightTruck: Optional[Decimal] = None
    Unloading: Optional[Decimal] = None
    OHD: Optional[Decimal] = None
    IFC: Optional[Decimal] = None
    WeighmentDiff: Optional[Decimal] = None
    CD: Optional[Decimal] = None
    SWECharge: Optional[Decimal] = None
    CRS: Optional[Decimal] = None
    IncCharge: Optional[Decimal] = None
    ShortLnthCharge: Optional[Decimal] = None
    SpeciFicLnthCharge: Optional[Decimal] = None
    ExtraCharge: Optional[Decimal] = None
    Fluctuation: Optional[Decimal] = None
    Commission: Optional[Decimal] = None
    Misc: Optional[Decimal] = None
    Testing: Optional[Decimal] = None
    MOUTOD: Optional[Decimal] = None
    SplDisc: Optional[Decimal] = None
    JC: Optional[Decimal] = None

    # Calculated + GST
    basicRate: Optional[Decimal] = None
    totRate: Optional[Decimal] = None
    gstMode: Optional[str] = None
    IGST: Optional[Decimal] = None
    CGST: Optional[Decimal] = None
    SGST: Optional[Decimal] = None
    totAmount: Optional[Decimal] = None

    # Gross
    totalAmount: Optional[Decimal] = None
    totalGst: Optional[Decimal] = None
    grossExForPrice: Optional[Decimal] = None

    # Goal-seek trail
    targetTotRate: Optional[Decimal] = None
    adjustableHeads: Optional[str] = None

    class Config:
        from_attributes = True


class ViabilityLineUpdate(BaseModel):
    """Partial update. Any field not supplied is left alone.

    Sending itemDia triggers a TPWGST refresh on the server.
    """
    itemName: Optional[str] = None
    itemGradeName: Optional[str] = None
    itemDia: Optional[str] = None
    itemLength: Optional[str] = None
    itemUnit: Optional[str] = None
    orderedQty: Optional[Decimal] = None
    modeOfDispatch: Optional[str] = None
    gstMode: Optional[str] = None

    TPWGST: Optional[Decimal] = None
    Marketing: Optional[Decimal] = None
    FreightTrailer: Optional[Decimal] = None
    FreightTruck: Optional[Decimal] = None
    Unloading: Optional[Decimal] = None
    OHD: Optional[Decimal] = None
    IFC: Optional[Decimal] = None
    WeighmentDiff: Optional[Decimal] = None
    CD: Optional[Decimal] = None
    SWECharge: Optional[Decimal] = None
    CRS: Optional[Decimal] = None
    IncCharge: Optional[Decimal] = None
    ShortLnthCharge: Optional[Decimal] = None
    SpeciFicLnthCharge: Optional[Decimal] = None
    ExtraCharge: Optional[Decimal] = None
    Fluctuation: Optional[Decimal] = None
    Commission: Optional[Decimal] = None
    Misc: Optional[Decimal] = None
    Testing: Optional[Decimal] = None
    MOUTOD: Optional[Decimal] = None
    SplDisc: Optional[Decimal] = None
    JC: Optional[Decimal] = None


class GoalSeekRequest(BaseModel):
    """Body for goal-seek: user supplies a target totRate and the subset of
    adjustable heads that are allowed to change. Heads not in this list stay
    locked. Delta is distributed proportional to each selected head's |value|;
    if all selected heads are zero we fall back to equal split.
    """
    target: Decimal
    adjustableHeads: List[str]


class ViabilitySheetResponse(BaseModel):
    viabilityId: int
    companyId: int
    quotId: int
    status: str
    approvedby: Optional[int] = None
    approvedon: Optional[datetime] = None
    isActive: bool
    lines: List[ViabilityLineResponse] = []

    class Config:
        from_attributes = True


class WorkingSheetLine(BaseModel):
    """Lightweight snapshot of a QuotDetails row — used for the 'Working Sheet'
    half of the dual view. Pure pass-through; the client never edits this.
    """
    quotDtlId: int
    itemName: Optional[str] = None
    itemGradeName: Optional[str] = None
    itemDia: Optional[str] = None
    itemLength: Optional[str] = None
    itemUnit: Optional[str] = None
    quantity: Optional[Decimal] = None

    TPWGST: Optional[Decimal] = None
    Marketing: Optional[Decimal] = None
    FreightTrailer: Optional[Decimal] = None
    FreightTruck: Optional[Decimal] = None
    Unloading: Optional[Decimal] = None
    OHD: Optional[Decimal] = None
    IFC: Optional[Decimal] = None
    WeighmentDiff: Optional[Decimal] = None
    CD: Optional[Decimal] = None
    SWECharge: Optional[Decimal] = None
    CRS: Optional[Decimal] = None
    IncCharge: Optional[Decimal] = None
    ShortLnthCharge: Optional[Decimal] = None
    SpeciFicLnthCharge: Optional[Decimal] = None
    ExtraCharge: Optional[Decimal] = None
    Fluctuation: Optional[Decimal] = None
    Commission: Optional[Decimal] = None
    Misc: Optional[Decimal] = None
    Testing: Optional[Decimal] = None
    MOUTOD: Optional[Decimal] = None
    SplDisc: Optional[Decimal] = None
    JC: Optional[Decimal] = None

    totRate: Optional[Decimal] = None
    gstMode: Optional[str] = None
    IGST: Optional[Decimal] = None
    CGST: Optional[Decimal] = None
    SGST: Optional[Decimal] = None
    totAmount: Optional[Decimal] = None
    modeOfDispatch: Optional[str] = None

    class Config:
        from_attributes = True


class ViabilityBundleResponse(BaseModel):
    """Combined payload for the main GET — lets the client render both tables
    without a second round trip.
    """
    workingSheet: List[WorkingSheetLine]
    viability: ViabilitySheetResponse
