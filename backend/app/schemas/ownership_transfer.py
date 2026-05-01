from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TransferRequest(BaseModel):
    entityType: str  # "enquiry" or "quotation"
    entityId: int
    toUserId: int
    remarks: Optional[str] = None


class TransferAction(BaseModel):
    remarks: Optional[str] = None


class TransferResponse(BaseModel):
    transferId: int
    companyId: int
    entityType: str
    entityId: int
    fromUserId: int
    fromUserName: Optional[str] = None
    toUserId: int
    toUserName: Optional[str] = None
    requestedBy: int
    requestedByName: Optional[str] = None
    requestedOn: datetime
    status: str
    approvedBy: Optional[int] = None
    approvedByName: Optional[str] = None
    approvedOn: Optional[datetime] = None
    remarks: Optional[str] = None

    class Config:
        from_attributes = True
