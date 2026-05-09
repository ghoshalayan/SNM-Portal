from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, model_validator


class QuotPOWorkingSheetLineBody(BaseModel):
    """Body for create / update of one Final Working Sheet line.
    Mirrors ``QuotDetails`` editable shape so the existing frontend
    grid component can post the same payload to a different endpoint.
    """
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

    # Calculated / GST
    basicRate: Optional[float] = None
    totRate: Optional[float] = None
    gstMode: Optional[str] = None
    IGST: Optional[float] = None
    CGST: Optional[float] = None
    SGST: Optional[float] = None
    totAmount: Optional[float] = None


class QuotPOWorkingSheetLineResponse(QuotPOWorkingSheetLineBody):
    poWorkingSheetId: int
    companyId: int
    quotPOId: int
    sourceQuotDtlId: Optional[int] = None
    isActive: bool = True
    createdby: Optional[int] = None
    createdon: Optional[datetime] = None
    lastupdateby: Optional[int] = None
    lastupdateon: Optional[datetime] = None
    # Convenience alias so the existing line-grid component (which
    # reads ``row.quotDtlId`` from QuotDetails responses) works in PO
    # mode without per-PK branching. Mirrors ``poWorkingSheetId``.
    quotDtlId: Optional[int] = None

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _alias_pk(cls, data: Any) -> Any:
        # When Pydantic builds from an ORM row (``from_attributes``
        # path), ``data`` is the SQLAlchemy ``QuotPOWorkingSheet``
        # instance. Stitch a dict that includes the PK alias so
        # callers expecting ``quotDtlId`` get a value.
        if isinstance(data, dict):
            if "quotDtlId" not in data and "poWorkingSheetId" in data:
                data = {**data, "quotDtlId": data["poWorkingSheetId"]}
            return data
        if hasattr(data, "poWorkingSheetId"):
            # ORM instance path: build a dict of every relevant column +
            # the alias. Pydantic will then validate normally.
            cols = (
                "poWorkingSheetId", "companyId", "quotPOId",
                "sourceQuotDtlId",
                "itemid", "itemName", "itemGradeName", "itemDia",
                "itemLength", "itemUnit", "quantity",
                "TPWGST", "Marketing", "FreightTrailer", "FreightTruck",
                "Unloading", "OHD", "IFC", "WeighmentDiff", "CD",
                "SWECharge", "CRS", "IncCharge", "ShortLnthCharge",
                "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
                "Commission", "Misc", "Testing", "MOUTOD", "SplDisc",
                "JC", "modeOfDispatch",
                "basicRate", "totRate", "gstMode",
                "IGST", "CGST", "SGST", "totAmount",
                "isActive", "createdby", "createdon",
                "lastupdateby", "lastupdateon",
            )
            merged: dict[str, Any] = {
                k: getattr(data, k, None) for k in cols
            }
            merged["quotDtlId"] = merged.get("poWorkingSheetId")
            return merged
        return data
