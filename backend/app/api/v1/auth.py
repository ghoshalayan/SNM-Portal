from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.security import decode_token, verify_password, hash_password
from app.core.rate_limit import login_rate_limiter
from app.models.user import User
from app.models.role import Role
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    SelectCompanyRequest,
    TokenResponse,
    RefreshTokenRequest,
    CompanyInfo,
    ChangePasswordRequest,
)
from app.services.auth_service import (
    authenticate_user,
    get_user_companies,
    create_temp_token,
    create_full_tokens,
    validate_company_access,
)

router = APIRouter()
security = HTTPBearer()


def _build_token_response(db: Session, user_id: int, company_info: dict) -> TokenResponse:
    # Defense-in-depth: validate_company_access() already binds user→company,
    # but we explicitly company-scope the role fetch here too so a
    # mis-assembled company_info dict can never surface another tenant's role.
    user = db.query(User).filter(
        User.userId == user_id,
        User.isActive == True,
    ).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    role = db.query(Role).filter(
        Role.roleId == company_info["roleId"],
        Role.companyId == company_info["companyId"],
        Role.isActive == True,
    ).first()
    tokens = create_full_tokens(
        user_id=user_id,
        company_id=company_info["companyId"],
        role_id=company_info["roleId"],
        is_super_admin=company_info["isSuperAdmin"],
    )
    return TokenResponse(
        **tokens,
        tokenType="bearer",
        userId=user_id,
        userName=user.userName,
        companyId=company_info["companyId"],
        companyName=company_info["companyName"],
        roleId=company_info["roleId"],
        roleName=company_info["roleName"],
        isSuperAdmin=company_info["isSuperAdmin"],
        numGenMode=role.numGenMode if role else "own_code",
    )


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, raw_request: Request, db: Session = Depends(get_db)):
    # Rate limit check — blocks if too many recent failures from this IP
    login_rate_limiter.check(raw_request)

    try:
        user = authenticate_user(db, request.userLogin, request.password)
    except HTTPException:
        login_rate_limiter.record_failure(raw_request)
        raise

    login_rate_limiter.record_success(raw_request)

    companies = get_user_companies(db, user.userId)

    if not companies:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not mapped to any company",
        )

    temp_token = create_temp_token(user.userId)

    return LoginResponse(
        tempToken=temp_token,
        userId=user.userId,
        userName=user.userName,
        companies=[CompanyInfo(**c) for c in companies],
    )


@router.post("/select-company", response_model=TokenResponse)
def select_company(
    request: SelectCompanyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    company_info = validate_company_access(db, user_id, request.companyId)
    return _build_token_response(db, user_id, company_info)


@router.post("/switch-company", response_model=TokenResponse)
def switch_company(
    request: SelectCompanyRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("user_id")
    company_info = validate_company_access(db, user_id, request.companyId)
    return _build_token_response(db, user_id, company_info)


@router.get("/my-companies", response_model=list[CompanyInfo])
def my_companies(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all companies the authenticated user can access.
    Super admins get ALL active companies; regular users get only mapped ones."""
    companies = get_user_companies(db, current_user.user_id)
    return [CompanyInfo(**c) for c in companies]


@router.post("/change-password", status_code=200)
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Authenticated user changes their own password.

    Requires the current password as proof-of-possession (defends against
    a stolen but locked-screen browser session). The new password is
    bcrypt-hashed via the shared security module so it stays consistent
    with the login-time verification path.
    """
    new_pw = (payload.newPassword or "").strip()
    if len(new_pw) < 6:
        raise HTTPException(
            status_code=400,
            detail="New password must be at least 6 characters.",
        )

    user = db.query(User).filter(
        User.userId == current_user.user_id,
        User.isActive == True,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.currentPassword or "", user.userPassword):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect.",
        )

    if verify_password(new_pw, user.userPassword):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the current password.",
        )

    user.userPassword = hash_password(new_pw)
    user.lastupdateby = current_user.user_id
    db.commit()
    return {"message": "Password updated"}


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = decode_token(request.refreshToken)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user_id = payload["user_id"]
    company_id = payload.get("company_id")

    user = db.query(User).filter(User.userId == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    company_info = validate_company_access(db, user_id, company_id)
    return _build_token_response(db, user_id, company_info)
