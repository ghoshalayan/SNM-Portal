from sqlalchemy.orm import Session
from typing import List
from app.models.menu import MenuMaster
from app.models.role_menu_map import RoleMenuMap


def build_menu_tree(menus: List[MenuMaster], parent_id=None) -> List[dict]:
    tree = []
    for menu in sorted(menus, key=lambda m: m.menuOrder or 0):
        if menu.parentMenuId == parent_id:
            node = {
                "menuId": menu.menuId,
                "menuName": menu.menuName,
                "menuUrl": menu.menuUrl,
                "menuIcon": menu.menuIcon,
                "menuOrder": menu.menuOrder,
                "children": build_menu_tree(menus, menu.menuId),
            }
            tree.append(node)
    return tree


def get_user_menu_tree(db: Session, company_id: int, role_id: int) -> List[dict]:
    """Get menu tree filtered by role permissions (CanRead=True)."""
    permitted_menu_ids = (
        db.query(RoleMenuMap.menuId)
        .filter(
            RoleMenuMap.roleId == role_id,
            RoleMenuMap.CanRead == True,
            RoleMenuMap.isActive == True,
        )
        .all()
    )
    permitted_ids = {m[0] for m in permitted_menu_ids}

    all_menus = (
        db.query(MenuMaster)
        .filter(
            MenuMaster.companyId == company_id,
            MenuMaster.isActive == True,
        )
        .all()
    )

    # Include parent menus even if they don't have direct CanRead
    # (so the tree structure is maintained)
    menu_map = {m.menuId: m for m in all_menus}
    visible_ids = set()
    for mid in permitted_ids:
        current = mid
        while current is not None:
            visible_ids.add(current)
            parent = menu_map.get(current)
            current = parent.parentMenuId if parent else None

    visible_menus = [m for m in all_menus if m.menuId in visible_ids]
    return build_menu_tree(visible_menus)
