from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User, UserRoleMap
from app.models.company import Company
from app.models.role import Role
from app.core.security import verify_password, create_access_token, create_refresh_token


def authenticate_user(db: Session, user_login: str, password: str) -> User:
    user = db.query(User).filter(
        User.userLogin == user_login,
        User.isActive == True,
    ).first()

    if not user or not verify_password(password, user.userPassword):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return user


def _get_super_admin_role(db: Session, user_id: int):
    """Return (UserRoleMap, Role) if user has any active super admin mapping, else None."""
    return (
        db.query(UserRoleMap, Role)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.isActive == True,
            Role.IsSuperAdmin == True,
        )
        .first()
    )


def get_user_companies(db: Session, user_id: int) -> list[dict]:
    # Super admin sees ALL active companies (company-independent)
    sa = _get_super_admin_role(db, user_id)
    if sa:
        urm, home_role = sa
        companies = db.query(Company).filter(Company.isActive == True).all()

        # Build a map of company-local SA roles so JWT gets the right roleId
        local_sa_roles = {
            r.companyId: r
            for r in db.query(Role).filter(
                Role.IsSuperAdmin == True,
                Role.isActive == True,
            ).all()
        }

        result = []
        for c in companies:
            local_role = local_sa_roles.get(c.companyId, home_role)
            result.append({
                "companyId": c.companyId,
                "companyName": c.companyName,
                "roleId": local_role.roleId,
                "roleName": local_role.roleName,
                "isDefault": c.companyId == urm.companyId,
                "isSuperAdmin": True,
            })
        return result

    # Regular user: only mapped companies
    mappings = (
        db.query(UserRoleMap, Company, Role)
        .join(Company, UserRoleMap.companyId == Company.companyId)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.isActive == True,
            Company.isActive == True,
            Role.isActive == True,
        )
        .all()
    )

    return [
        {
            "companyId": mapping.companyId,
            "companyName": company.companyName,
            "roleId": mapping.roleId,
            "roleName": role.roleName,
            "isDefault": mapping.isDefault,
            "isSuperAdmin": False,
        }
        for mapping, company, role in mappings
    ]


def create_temp_token(user_id: int) -> str:
    return create_access_token({"user_id": user_id, "temp": True})


def create_full_tokens(
    user_id: int,
    company_id: int,
    role_id: int,
    is_super_admin: bool,
) -> dict:
    payload = {
        "user_id": user_id,
        "company_id": company_id,
        "role_id": role_id,
        "is_super_admin": is_super_admin,
    }
    return {
        "accessToken": create_access_token(payload),
        "refreshToken": create_refresh_token(payload),
    }


def validate_company_access(db: Session, user_id: int, company_id: int) -> dict:
    # Super admin can access ANY active company
    sa = _get_super_admin_role(db, user_id)
    if sa:
        _, home_role = sa
        company = db.query(Company).filter(
            Company.companyId == company_id,
            Company.isActive == True,
        ).first()
        if not company:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Company not found or inactive",
            )
        # Prefer the target company's own SA role (created by seeder) so that
        # Role.companyId matches JWT company_id on subsequent permission checks.
        local_sa_role = db.query(Role).filter(
            Role.companyId == company_id,
            Role.IsSuperAdmin == True,
            Role.isActive == True,
        ).first()
        role = local_sa_role or home_role
        return {
            "companyId": company.companyId,
            "companyName": company.companyName,
            "roleId": role.roleId,
            "roleName": role.roleName,
            "isSuperAdmin": True,
        }

    # Regular user: must have explicit mapping with an active, company-scoped role
    mapping = (
        db.query(UserRoleMap, Company, Role)
        .join(Company, UserRoleMap.companyId == Company.companyId)
        .join(Role, UserRoleMap.roleId == Role.roleId)
        .filter(
            UserRoleMap.userId == user_id,
            UserRoleMap.companyId == company_id,
            UserRoleMap.isActive == True,
            Role.isActive == True,
            Role.companyId == company_id,
        )
        .first()
    )

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this company",
        )

    urm, company, role = mapping
    return {
        "companyId": company.companyId,
        "companyName": company.companyName,
        "roleId": role.roleId,
        "roleName": role.roleName,
        "isSuperAdmin": role.IsSuperAdmin,
    }
