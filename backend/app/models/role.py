from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class Role(Base, AuditMixin):
    __tablename__ = "RoleMaster"

    roleId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    roleName = Column(String(100), nullable=False)

    # ---- Super admin flags ----
    IsSuperAdmin = Column(Boolean, default=False, nullable=False)
    # Company admin: full access within a single company (bypasses F5/F6)
    IsCompanyAdmin = Column(Boolean, default=False, nullable=False)

    # ---- Number generation ----
    # own_code | parent_code | select_code
    numGenMode = Column(String(20), default="own_code", nullable=False)

    # ---- Hierarchy flags ----
    # Downward visibility: how many levels of children visible (-1 = unlimited, 0 = none)
    downwardLevels = Column(Integer, default=-1, nullable=False)
    # Upward visibility: how many levels of parents visible (-1 = unlimited, 0 = none)
    upwardLevels = Column(Integer, default=0, nullable=False)
    # When walking upward, also include each ancestor's full subtree
    includeSubtreeOnUpward = Column(Boolean, default=True, nullable=False)
    # Peer access: see records of users with same reportTo (siblings)
    peerAccess = Column(Boolean, default=False, nullable=False)
    # If peerAccess=True, also include peers' subtrees
    peerSubtree = Column(Boolean, default=False, nullable=False)

    # ---- Location flags ----
    # If True, location filtering applies; False = bypass F6 (admin-like)
    locationScopeRequired = Column(Boolean, default=True, nullable=False)
    # KRO-style: user's own location must be subset of their reportTo's locations
    enforceChildLocationSubset = Column(Boolean, default=False, nullable=False)

    # ---- Misc ----
    # Hierarchy rank (higher = more authority, 0 = lowest)
    roleLevel = Column(Integer, default=0, nullable=False)
    # Can approve ownership transfer requests (reserved for future workflow)
    canApproveTransfers = Column(Boolean, default=False, nullable=False)

    # ---- Legacy (kept for backward compat; access_service prefers upwardLevels) ----
    upwardVisibilityLevels = Column(Integer, default=0, nullable=False)
