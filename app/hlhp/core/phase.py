"""Time-of-day phase resolution per HLHP Engine Implementation Spec v2 §7."""

from __future__ import annotations

from datetime import datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

DayPhase = Literal["morning", "evening"]
TimeOfDayPhase = Literal[
    "morning_prep", "evening_recovery", "both_phases", "any_time", ""
]

_MORNING_START = time(4, 0)
_MORNING_END = time(15, 59, 59)


def resolve_day_phase(when: datetime | None = None, tz: str = "Asia/Kolkata") -> DayPhase:
    """
    AM = 04:00–15:59 local, PM = 16:00–03:59 local.
    """
    dt = when or datetime.now(ZoneInfo(tz))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    else:
        dt = dt.astimezone(ZoneInfo(tz))
    t = dt.time()
    if _MORNING_START <= t <= _MORNING_END:
        return "morning"
    return "evening"


def matches_time_of_day(row_phase: str, day_phase: DayPhase) -> bool:
    phase = (row_phase or "any_time").strip().lower()
    if phase in {"", "any_time", "both_phases"}:
        return True
    if phase == "morning_prep":
        return day_phase == "morning"
    if phase == "evening_recovery":
        return day_phase == "evening"
    return True


def phase_used_label(row_phase: str, day_phase: DayPhase) -> str:
    phase = (row_phase or "any_time").strip().lower()
    if phase == "evening_recovery" or (phase == "both_phases" and day_phase == "evening"):
        return "evening_recovery"
    if phase == "morning_prep" or (phase == "both_phases" and day_phase == "morning"):
        return "morning_prep"
    return "morning_prep" if day_phase == "morning" else "evening_recovery"
