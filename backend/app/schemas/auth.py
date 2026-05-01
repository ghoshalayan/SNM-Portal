from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    userLogin: str
    password: str


class CompanyInfo(BaseModel):
    companyId: int
    companyName: str
    roleId: int
    roleName: str
    isDefault: bool
    isSuperAdmin: bool = False

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    tempToken: str
    userId: int
    userName: str
    companies: list[CompanyInfo]


class SelectCompanyRequest(BaseModel):
    companyId: int


class TokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    userId: int
    userName: str
    companyId: int
    companyName: str
    roleId: int
    roleName: str
    isSuperAdmin: bool
    numGenMode: str = "own_code"


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


class TokenPayload(BaseModel):
    user_id: int
    company_id: Optional[int] = None
    role_id: Optional[int] = None
    is_super_admin: bool = False
    type: str = "access"
