from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class RoleMappingCreate(BaseModel):
    companyId: int
    roleId: int
    isDefault: bool = False
    reportTo: Optional[int] = None


class UserCreate(BaseModel):
    userName: str
    userCode: Optional[str] = None
    userEmail: Optional[str] = None
    userPhone: Optional[str] = None
    userDesignation: Optional[str] = None
    userLogin: str
    userPassword: str
    companyId: int
    reportTo: Optional[int] = None
    roleMappings: List[RoleMappingCreate] = []


class UserUpdate(BaseModel):
    userName: Optional[str] = None
    userCode: Optional[str] = None
    userEmail: Optional[str] = None
    userPhone: Optional[str] = None
    userDesignation: Optional[str] = None
    reportTo: Optional[int] = None


class UserResponse(BaseModel):
    userId: int
    companyId: int
    userName: str
    userCode: Optional[str] = None
    userEmail: Optional[str] = None
    userPhone: Optional[str] = None
    userDesignation: Optional[str] = None
    userLogin: str
    reportTo: Optional[int] = None
    reportToName: Optional[str] = None
    isActive: bool
    createdon: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserRoleMapResponse(BaseModel):
    userRoleMapId: int
    companyId: int
    roleId: int
    isDefault: bool
    reportTo: Optional[int] = None
    reportToName: Optional[str] = None

    class Config:
        from_attributes = True


# --- User Location Mapping ---

class LocationMappingCreate(BaseModel):
    countryid: int
    stateid: int
    districtid: Optional[int] = None


class UserLocationMapResponse(BaseModel):
    userLocationMapId: int
    userId: int
    companyId: int
    countryid: int
    stateid: int
    districtid: Optional[int] = None

    class Config:
        from_attributes = True


class DistrictNode(BaseModel):
    districtid: int
    districtName: str


class StateNode(BaseModel):
    stateid: int
    stateName: str
    districts: List[DistrictNode] = []


class CountryNode(BaseModel):
    countryid: int
    countryName: str
    states: List[StateNode] = []


class UserLocationTreeNode(BaseModel):
    """Tree response: countries → states → districts for a user."""
    locations: List[CountryNode] = []
