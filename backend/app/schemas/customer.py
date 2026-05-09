from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


# --- Customer Master ---
class CustomerCreate(BaseModel):
    classificationId: Optional[int] = None
    customerCode: Optional[str] = None
    customerName: str
    GSTN: Optional[str] = None
    PAN: Optional[str] = None
    siteId: Optional[int] = None

class CustomerUpdate(CustomerCreate):
    customerName: Optional[str] = None

class CustomerContactResponse(BaseModel):
    customerContactId: int
    customerId: int
    contactTypeId: Optional[int] = None
    contactTypeName: Optional[str] = None
    contactPersonName: Optional[str] = None
    designation: Optional[str] = None
    personalPhone: Optional[str] = None
    personalEmail: Optional[str] = None
    officePhone: Optional[str] = None
    officeEmail: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    dist: Optional[str] = None
    birthday: Optional[date] = None
    anniversary: Optional[date] = None
    isActive: bool
    class Config:
        from_attributes = True

class CustomerSiteResponse(BaseModel):
    siteId: int
    customerId: int
    siteAddressCode: Optional[str] = None
    addressLine: Optional[str] = None
    state: Optional[str] = None
    dist: Optional[str] = None
    PIN: Optional[str] = None
    contactPerson1: Optional[str] = None
    contactPhone1: Optional[str] = None
    contactEmail1: Optional[str] = None
    contactPerson2: Optional[str] = None
    contactPhone2: Optional[str] = None
    contactEmail2: Optional[str] = None
    contactPerson3: Optional[str] = None
    contactPhone3: Optional[str] = None
    contactEmail3: Optional[str] = None
    isHeadOffice: Optional[bool] = False
    isAdHoc: Optional[bool] = False
    isActive: bool
    class Config:
        from_attributes = True

class CustomerResponse(BaseModel):
    customerId: int
    companyId: int
    classificationId: Optional[int] = None
    classificationName: Optional[str] = None
    customerCode: Optional[str] = None
    customerName: str
    GSTN: Optional[str] = None
    PAN: Optional[str] = None
    siteId: Optional[int] = None
    isActive: bool
    createdon: Optional[datetime] = None
    class Config:
        from_attributes = True

class CustomerDetailResponse(CustomerResponse):
    contacts: List[CustomerContactResponse] = []
    sites: List[CustomerSiteResponse] = []


# --- Customer Contact ---
class CustomerContactCreate(BaseModel):
    contactTypeId: Optional[int] = None
    contactPersonName: Optional[str] = None
    designation: Optional[str] = None
    personalPhone: Optional[str] = None
    personalEmail: Optional[str] = None
    officePhone: Optional[str] = None
    officeEmail: Optional[str] = None
    address: Optional[str] = None
    state: Optional[str] = None
    dist: Optional[str] = None
    birthday: Optional[date] = None
    anniversary: Optional[date] = None


# --- Customer Site ---
class CustomerSiteCreate(BaseModel):
    siteAddressCode: Optional[str] = None
    addressLine: Optional[str] = None
    state: Optional[str] = None
    dist: Optional[str] = None
    PIN: Optional[str] = None
    contactPerson1: Optional[str] = None
    contactPhone1: Optional[str] = None
    contactEmail1: Optional[str] = None
    contactPerson2: Optional[str] = None
    contactPhone2: Optional[str] = None
    contactEmail2: Optional[str] = None
    contactPerson3: Optional[str] = None
    contactPhone3: Optional[str] = None
    contactEmail3: Optional[str] = None
    isHeadOffice: Optional[bool] = False
