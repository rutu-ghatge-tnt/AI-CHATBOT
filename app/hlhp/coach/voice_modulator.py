from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.hlhp.coach.models import Tone
from app.hlhp.models.profile import StressLevel, UserProfile, SleepTime


def select_tone(profile: UserProfile, *, severity: str = "SOFT_ENV") -> Tone:
    if profile.stress_level in {StressLevel.HIGH, StressLevel.VERY_HIGH}:
        return "gentle"
    if profile.sleep_time in {SleepTime.LESS_THAN_5H, SleepTime.H5_6H}:
        return "gentle"
    if severity == "BLOCK_ENV":
        return "direct"
    return "informative"
