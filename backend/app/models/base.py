from sqlalchemy import Column, Integer, DateTime, Boolean
from sqlalchemy.orm import declared_attr

from app.core.timezone import now_ist


class AuditMixin:
    """Mixin for common audit fields across all tables.

    All timestamps are stored in IST (Indian Standard Time, UTC+5:30).
    """

    @declared_attr
    def createdon(cls):
        return Column(DateTime, default=now_ist, nullable=True)

    @declared_attr
    def createdby(cls):
        return Column(Integer, nullable=True)

    @declared_attr
    def lastupdateon(cls):
        return Column(DateTime, default=now_ist, onupdate=now_ist, nullable=True)

    @declared_attr
    def lastupdateby(cls):
        return Column(Integer, nullable=True)

    @declared_attr
    def isActive(cls):
        return Column(Boolean, default=True, nullable=False)
