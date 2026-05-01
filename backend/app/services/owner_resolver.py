"""Resolves the owner user for enquiry/quotation creation.

Based on the role's numGenMode:
- own_code: owner = current user
- parent_code: owner = current user's reportTo (company-scoped via UserRoleMap)
- select_code: owner = explicitly selected user (codeUserId)

Returns (user_id, user_code, role_id) tuple.
"""

from sqlalchemy.orm import Session
from app.core.dependencies import CurrentUser
from app.models.user import User, UserRoleMap
from app.models.role import Role


def resolve_owner(db: Session, current_user: CurrentUser, code_user_id: int = None) -> dict:
    """Returns dict with userId, userCode, roleId for the resolved owner."""
    role = db.query(Role).filter(Role.roleId == current_user.role_id).first()
    mode = role.numGenMode if role else "own_code"

    if mode == "select_code" and code_user_id:
        return _get_user_info(db, code_user_id, current_user.company_id)

    if mode == "parent_code":
        # Use company-scoped reportTo from UserRoleMap
        mapping = db.query(UserRoleMap).filter(
            UserRoleMap.userId == current_user.user_id,
            UserRoleMap.companyId == current_user.company_id,
            UserRoleMap.isActive == True,
        ).first()
        if mapping and mapping.reportTo:
            return _get_user_info(db, mapping.reportTo, current_user.company_id)
        # Fallback to own if no parent
        return _get_user_info(db, current_user.user_id, current_user.company_id)

    # own_code (default)
    return _get_user_info(db, current_user.user_id, current_user.company_id)


def _get_user_info(db: Session, user_id: int, company_id: int) -> dict:
    """Get userId, userCode, roleId for a user in a company."""
    user = db.query(User).filter(User.userId == user_id).first()
    user_code = (user.userCode or "USR") if user else "USR"

    # Get the user's role in this company
    mapping = db.query(UserRoleMap).filter(
        UserRoleMap.userId == user_id,
        UserRoleMap.companyId == company_id,
        UserRoleMap.isActive == True,
    ).first()
    role_id = mapping.roleId if mapping else None

    return {
        "userId": user_id,
        "userCode": user_code,
        "roleId": role_id,
    }
