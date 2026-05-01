from typing import Generator, Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import decode_token

security = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@dataclass
class CurrentUser:
    user_id: int
    company_id: int
    role_id: int
    is_super_admin: bool


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("user_id")
    company_id = payload.get("company_id")
    role_id = payload.get("role_id")

    if not user_id or not company_id or not role_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incomplete token payload — select a company first",
        )

    return CurrentUser(
        user_id=user_id,
        company_id=company_id,
        role_id=role_id,
        is_super_admin=payload.get("is_super_admin", False),
    )


def get_active_company(
    current_user: CurrentUser = Depends(get_current_user),
) -> int:
    return current_user.company_id


def require_permission(menu_name: str, action: str) -> Callable:
    """Dependency factory that checks RoleMenuMap for the given menu + action.

    Usage:
        @router.get("/items", dependencies=[Depends(require_permission("ItemGrade", "CanRead"))])
    """
    def checker(
        current_user: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if current_user.is_super_admin:
            return True

        from app.models.role_menu_map import RoleMenuMap
        from app.models.menu import MenuMaster

        mapping = (
            db.query(RoleMenuMap)
            .join(MenuMaster, RoleMenuMap.menuId == MenuMaster.menuId)
            .filter(
                RoleMenuMap.roleId == current_user.role_id,
                MenuMaster.menuName == menu_name,
                RoleMenuMap.isActive == True,
            )
            .first()
        )

        if not mapping:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No permission for {menu_name}",
            )

        action_map = {
            "CanAdd": mapping.CanAdd,
            "CanRead": mapping.CanRead,
            "CanEdit": mapping.CanEdit,
            "CanDelete": mapping.CanDelete,
        }

        if not action_map.get(action, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No {action} permission for {menu_name}",
            )

        return True

    return checker


def require_super_admin(
    current_user: CurrentUser = Depends(get_current_user),
):
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required",
        )
    return current_user
