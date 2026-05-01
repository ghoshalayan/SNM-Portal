"""Location-based access control: determines which locations a user can access.

Rules:
- SuperAdmin → no filter, access everything
- User with state mapping (no district) → full access to all districts in that state
- User with state+district mapping → only those specific districts
- No mappings → no location access (sees nothing location-filtered)
"""

from typing import Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models.user_location_map import UserLocationMap
from app.models.location import StateMaster, DistrictMaster


class LocationAccess:
    """Holds a user's resolved location jurisdiction."""

    def __init__(self, is_super_admin: bool = False):
        self.is_super_admin = is_super_admin
        # Pre-normalized lowercase sets for fast lookup
        self._full_states: Set[str] = set()          # states with all-district access
        self._specific: Set[Tuple[str, str]] = set()  # (state, district) pairs
        self._all_states: Set[str] = set()             # cached union
        self._all_states_original: Set[str] = set()    # original case for SQL IN

    def _add_full_state(self, state: str):
        self._full_states.add(state.strip().lower())
        self._all_states_original.add(state.strip())

    def _add_district(self, state: str, dist: str):
        self._specific.add((state.strip().lower(), dist.strip().lower()))
        self._all_states_original.add(state.strip())

    def can_access(self, state: Optional[str], dist: Optional[str]) -> bool:
        if self.is_super_admin:
            return True
        if not state:
            return True
        sl = state.strip().lower()
        if sl in self._full_states:
            return True
        if dist:
            return (sl, dist.strip().lower()) in self._specific
        return False

    @property
    def state_names(self) -> Set[str]:
        """All state names (original case) for SQL IN clauses."""
        return self._all_states_original

    def district_names_for_state(self, state: str) -> Optional[Set[str]]:
        """District names for a state. None = full state access."""
        sl = state.strip().lower()
        if sl in self._full_states:
            return None
        return {d for s, d in self._specific if s == sl}

    def build_sql_filter(self, state_col, dist_col, nullable_fk=None):
        """Build a SQLAlchemy filter expression for location access.

        state_col: the state column (e.g., CustomerSite.state)
        dist_col: the district column (e.g., CustomerSite.dist)
        nullable_fk: optional FK column that can be NULL (e.g., siteId) — NULL means no location, allow through
        """
        if self.is_super_admin:
            return None  # no filter needed

        conditions = []

        # Allow records with no location (NULL FK)
        if nullable_fk is not None:
            conditions.append(nullable_fk == None)

        # Full state access
        if self._full_states:
            full_state_names = {s for s in self._all_states_original
                                if s.strip().lower() in self._full_states}
            if full_state_names:
                conditions.append(state_col.in_(full_state_names))

        # Specific district access — build (state, dist) pairs
        for s_lower, d_lower in self._specific:
            # Find original-case names
            for orig_s in self._all_states_original:
                if orig_s.strip().lower() == s_lower:
                    conditions.append(
                        (state_col == orig_s) & (dist_col.ilike(d_lower))
                    )
                    break

        if not conditions:
            return False  # no access at all

        return or_(*conditions)


def get_location_access(
    db: Session,
    user_id: int,
    company_id: int,
    is_super_admin: bool,
    role_id: int = None,
) -> LocationAccess:
    """Build LocationAccess for a user."""
    access = LocationAccess(is_super_admin=is_super_admin)
    if is_super_admin:
        return access

    # Check if role has locationScopeRequired=False → skip location filtering
    if role_id:
        from app.models.role import Role
        role = db.query(Role.locationScopeRequired).filter(Role.roleId == role_id).first()
        if role and not role.locationScopeRequired:
            access.is_super_admin = True  # bypass location checks
            return access

    mappings = (
        db.query(
            StateMaster.StateName,
            DistrictMaster.districName,
        )
        .select_from(UserLocationMap)
        .join(StateMaster, StateMaster.stateid == UserLocationMap.stateid)
        .outerjoin(DistrictMaster, DistrictMaster.districtid == UserLocationMap.districtid)
        .filter(
            UserLocationMap.userId == user_id,
            UserLocationMap.companyId == company_id,
            UserLocationMap.isActive == True,
        )
        .all()
    )

    for state_name, district_name in mappings:
        if not district_name:
            access._add_full_state(state_name)
        else:
            access._add_district(state_name, district_name)

    return access
