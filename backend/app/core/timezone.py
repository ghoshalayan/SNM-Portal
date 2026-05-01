"""Application timezone utility.

All user-facing timestamps (createdon, lastupdateon, approvedon, etc.) are
stored as Indian Standard Time (IST = UTC+5:30) per business requirement.

JWT 'exp' claims and Azure SAS URLs intentionally remain in UTC because
they're consumed by external libraries / cloud services that expect UTC.

Use these helpers for every new timestamp:
    from app.core.timezone import now_ist, IST
    obj.createdon = now_ist()
"""

from datetime import datetime, timezone, timedelta

# UTC+5:30 — Asia/Kolkata (no DST)
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    """Current wall-clock time in IST as a NAIVE datetime
    (no tzinfo) so it can be stored directly in SQL Server DATETIME columns
    without driver-specific timezone conversions.
    """
    return datetime.now(IST).replace(tzinfo=None)


def now_ist_aware() -> datetime:
    """Current IST time WITH tzinfo attached. Use only when you explicitly
    need timezone-aware comparisons.
    """
    return datetime.now(IST)
