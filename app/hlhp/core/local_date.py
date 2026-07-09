"""Calendar-day helpers for HLHP streaks and daily aggregates (IST / Asia-Kolkata)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

HLHP_TZ = ZoneInfo("Asia/Kolkata")


def to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=HLHP_TZ)
    return dt.astimezone(HLHP_TZ)


def calendar_date(dt: datetime) -> date:
    """User-facing calendar day for streak keys."""
    return to_local(dt).date()


def calendar_date_key(dt: datetime) -> str:
    return calendar_date(dt).isoformat()


def today_local() -> date:
    return datetime.now(HLHP_TZ).date()
