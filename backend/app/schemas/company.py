from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CompanyCreate(BaseModel):
    companyName: str
    companyCode: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pinCode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    GSTN: Optional[str] = None
    PAN: Optional[str] = None
    logoUrl: Optional[str] = None
    MailFrom: Optional[str] = None
    MailPassword: Optional[str] = None
    SMTP: Optional[str] = None
    PortNo: Optional[str] = None


class CompanyUpdate(CompanyCreate):
    companyName: Optional[str] = None


class CompanyResponse(BaseModel):
    companyId: int
    companyName: str
    companyCode: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pinCode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    GSTN: Optional[str] = None
    PAN: Optional[str] = None
    logoUrl: Optional[str] = None
    MailFrom: Optional[str] = None
    SMTP: Optional[str] = None
    PortNo: Optional[str] = None
    isActive: bool
    createdon: Optional[datetime] = None

    class Config:
        from_attributes = True
