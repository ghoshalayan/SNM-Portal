"""Time-period → (start, end) resolver for the dashboard period selector.

Rolling-window semantics rather than calendar-aligned (e.g. "weekly"
means *the last 7 days*, not *the current calendar week*). Predictable,
no calendar-edge surprises, and matches the way most BI dashboards
default. ``custom`` lets the caller supply explicit dates for the
calendar-aligned case.

Returns timezone-aware UTC datetimes; the caller passes them straight
to SQLAlchemy ``text(...)`` parameter binding.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

# All values the API accepts for ``period``. Keep in sync with the
# frontend's selector chips; the validator below rejects anything else.
PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_MONTHLY = "monthly"
PERIOD_QUARTERLY = "quarterly"
PERIOD_YEARLY = "yearly"
PERIOD_LAST_5_YEARS = "last_5_years"
PERIOD_CUSTOM = "custom"

VALID_PERIODS = frozenset((
    PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY, PERIOD_QUARTERLY,
    PERIOD_YEARLY, PERIOD_LAST_5_YEARS, PERIOD_CUSTOM,
))

# Days-back for each rolling preset.
_PRESET_DAYS = {
    PERIOD_DAILY: 1,
    PERIOD_WEEKLY: 7,
    PERIOD_MONTHLY: 30,
    PERIOD_QUARTERLY: 90,
    PERIOD_YEARLY: 365,
    PERIOD_LAST_5_YEARS: 5 * 365,
}


class InvalidPeriodError(ValueError):
    pass


def resolve_period(
    period: Optional[str],
    *,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Optional[Tuple[datetime, datetime]]:
    """Map a period descriptor to a concrete (start, end) datetime pair.

    Returns ``None`` when ``period`` is None/empty (caller passes no time
    bindings — KPI runs against the full history).

    ``custom`` requires both ``start_date`` and ``end_date``. Other periods
    ignore those args.
    """
    if not period:
        return None

    if period not in VALID_PERIODS:
        raise InvalidPeriodError(
            f"Unknown period '{period}'. Allowed: {sorted(VALID_PERIODS)}"
        )

    now = now or datetime.now(timezone.utc)

    if period == PERIOD_CUSTOM:
        if start_date is None or end_date is None:
            raise InvalidPeriodError(
                "Custom period requires both start_date and end_date."
            )
        if end_date < start_date:
            raise InvalidPeriodError("end_date must be >= start_date.")
        return _ensure_utc(start_date), _ensure_utc(end_date)

    days = _PRESET_DAYS[period]
    return now - timedelta(days=days), now


def _ensure_utc(dt: datetime) -> datetime:
    """Coerce a naive datetime to UTC; pass through aware ones unchanged.

    Avoids "naive vs aware" comparison errors when the SQL Server driver
    serializes the value.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
