from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class DiaBreakupEntry(BaseModel):
    """Row in the auto-computed diawise breakup table."""
    dia: Optional[str] = None
    qty: Optional[Decimal] = None
    amount: Optional[Decimal] = None


class AnnexureResponse(BaseModel):
    annexureId: int
    companyId: int
    quotId: int
    viabilityId: Optional[int] = None
    status: str

    # Phase 1 versioning + Phase 3 freshness pointers.
    parentAnnexureId: Optional[int] = None
    versionNo: Optional[int] = 1
    sourcedFromQuotationVersion: Optional[int] = None
    sourcedFromPOVersion: Optional[int] = None
    sourcedFromViabilityVersion: Optional[int] = None

    # Header
    clientName: Optional[str] = None
    customerPONo: Optional[str] = None
    customerPODate: Optional[date] = None
    totalBillableAmount: Optional[Decimal] = None
    totalQuantityMT: Optional[Decimal] = None
    addressedTo: Optional[str] = None

    # Body
    invoicing: Optional[str] = None
    transportationMode: Optional[str] = None
    tcType: Optional[str] = None
    paymentTerms: Optional[str] = None
    loadabilityQty: Optional[Decimal] = None
    transportChargesPerMT: Optional[Decimal] = None
    transportChargesFOR: Optional[str] = None
    specificLength: Optional[str] = None
    tolerance: Optional[str] = None
    deliverySchedule: Optional[str] = None
    transportRealizationPerMT: Optional[Decimal] = None
    panNo: Optional[str] = None
    gstNo: Optional[str] = None
    contactPerson: Optional[str] = None
    contactPersonNumber: Optional[str] = None
    billingAddress: Optional[str] = None
    consigneeAddress: Optional[str] = None
    qualityFe: Optional[str] = None
    qualityStandard: Optional[str] = None
    qualityStandardLength: Optional[str] = None
    companyName: Optional[str] = None
    billsTo: Optional[str] = None
    totalOutstanding: Optional[Decimal] = None
    overdueOutstanding: Optional[Decimal] = None
    diawiseBreakup: List[DiaBreakupEntry] = []
    unloadingScope: Optional[str] = None
    unloadingRate: Optional[Decimal] = None
    remarks: Optional[str] = None

    # Signatures
    preparedByUserId: Optional[int] = None
    preparedByName: Optional[str] = None
    checkedByUserId: Optional[int] = None
    checkedByName: Optional[str] = None
    approvedByUserId: Optional[int] = None
    approvedByName: Optional[str] = None
    approvedon: Optional[datetime] = None

    isActive: bool

    class Config:
        from_attributes = True


class AnnexureUpdate(BaseModel):
    """All fields optional; whichever keys are sent get updated. Diawise
    breakup can be re-sent as an array (overwrites the stored JSON)."""
    # Header
    addressedTo: Optional[str] = None
    # Body
    invoicing: Optional[str] = None
    transportationMode: Optional[str] = None
    tcType: Optional[str] = None
    paymentTerms: Optional[str] = None
    loadabilityQty: Optional[Decimal] = None
    transportChargesPerMT: Optional[Decimal] = None
    transportChargesFOR: Optional[str] = None
    specificLength: Optional[str] = None
    tolerance: Optional[str] = None
    deliverySchedule: Optional[str] = None
    transportRealizationPerMT: Optional[Decimal] = None
    panNo: Optional[str] = None
    gstNo: Optional[str] = None
    contactPerson: Optional[str] = None
    contactPersonNumber: Optional[str] = None
    billingAddress: Optional[str] = None
    consigneeAddress: Optional[str] = None
    qualityFe: Optional[str] = None
    qualityStandard: Optional[str] = None
    qualityStandardLength: Optional[str] = None
    companyName: Optional[str] = None
    billsTo: Optional[str] = None
    totalOutstanding: Optional[Decimal] = None
    overdueOutstanding: Optional[Decimal] = None
    diawiseBreakup: Optional[List[DiaBreakupEntry]] = None
    unloadingScope: Optional[str] = None
    unloadingRate: Optional[Decimal] = None
    remarks: Optional[str] = None

    # Signatures (prepared/checked names are editable, approver is set by /approve)
    preparedByName: Optional[str] = None
    checkedByName: Optional[str] = None
