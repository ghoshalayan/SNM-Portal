from typing import List, Literal, Optional
from datetime import date, datetime
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
    # Cycle context — needed by the FE so the Re-generate picker can
    # scope its FWS-snapshot lookup to the correct cycle. Missing this
    # field caused the dialog to silently fall back to the legacy
    # confirm-only flow.
    quotOrderCycleId: Optional[int] = None
    status: str
    approvedby: Optional[int] = None
    approvedon: Optional[datetime] = None
    isActive: bool
    # Phase 1 versioning + Phase 3 freshness pointer.
    parentViabilityId: Optional[int] = None
    versionNo: Optional[int] = 1
    sourcedFromPOVersion: Optional[int] = None
    # TP-Cost sourcing toggle (Viability TP-Cost CR). Mode + selected date
    # persist on the sheet so the frontend toggle reflects the user's
    # last pick on re-open.
    #
    # ``po_working_sheet`` doesn't query the rate table — it reads the
    # TPWGST that was frozen on the matching Final Working Sheet line
    # when the PO was captured. Useful when the user wants to model
    # margin against the price that was actually committed to.
    tpCostMode: Optional[Literal["as_of_date", "po_working_sheet"]] = None
    tpCostAsOfDate: Optional[date] = None
    lines: List[ViabilityLineResponse] = []

    class Config:
        from_attributes = True


class RefreshTpCostRequest(BaseModel):
    """Body for ``POST /viability/{vid}/refresh-tp-cost``.

    ``mode`` selects the TP-Cost source:
      - ``as_of_date``: use the rate effective on ``asOfDate``
        (NULL = today, no date supplied).
      - ``po_working_sheet``: use the TPWGST that was captured on the
        matching Final Working Sheet line when the PO was taken — no
        rate-table lookup at all.

    ``overwriteAll`` controls collision behaviour with manual edits:
      - ``False`` (default): only refresh rows whose TPWGST matches
        *some* historical RawMaterialCost rate for that dia. Rows
        whose TPWGST doesn't match any historical rate are treated as
        hand-tuned and left alone.
      - ``True``: clobber every row's TPWGST with the new source value.

    The frontend pre-confirms with a dialog before sending
    ``overwriteAll=True`` so users don't lose manual work by accident.
    """
    mode: Literal["as_of_date", "po_working_sheet"]
    asOfDate: Optional[date] = None
    overwriteAll: bool = False


class RefreshTpCostLineResult(BaseModel):
    """Per-line outcome of a TP-Cost refresh."""
    viabilityLineId: int
    itemDia: Optional[str] = None
    previousTpwgst: Optional[Decimal] = None
    newTpwgst: Optional[Decimal] = None
    status: Literal["updated", "skipped_manual", "missing_rate", "no_change"]


class RefreshTpCostResponse(BaseModel):
    """Summary of the refresh + the updated sheet so the client can
    re-render without a second round-trip."""
    updatedCount: int
    skippedManualCount: int
    missingRateCount: int
    perLine: List[RefreshTpCostLineResult]
    sheet: ViabilitySheetResponse


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

    ``hasPoWorkingSheet`` tells the frontend whether the "LTP on WS @PO"
    toggle option is available (a PO exists for this quotation and has
    at least one Final Working Sheet row to copy TPWGST from).
    """
    workingSheet: List[WorkingSheetLine]
    viability: ViabilitySheetResponse
    hasPoWorkingSheet: bool = False
