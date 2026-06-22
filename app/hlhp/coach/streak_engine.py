from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.hlhp.coach.models import StreakRecord


def streak_key(uvi_band: str, routine_action: str) -> str:
    return f"{uvi_band}_{routine_action}"


def compute_streak_after_tap(
    record: StreakRecord | None,
    *,
    streak_key_val: str,
    today: date,
    tapped_at: datetime,
) -> StreakRecord:
    if record is None:
        return StreakRecord(
            streak_key=streak_key_val,
            consecutive_days=1,
            last_increment_at=tapped_at,
            longest_ever=1,
        )

    last = record.last_increment_at.date() if record.last_increment_at else None
    if last == today:
        return record

    gap = (today - last).days if last else 999
    if gap > 2:
        consecutive = 1
    else:
        consecutive = record.consecutive_days + 1

    longest = max(record.longest_ever, consecutive)
    return StreakRecord(
        streak_key=record.streak_key,
        consecutive_days=consecutive,
        last_increment_at=tapped_at,
        longest_ever=longest,
    )


def current_streak(record: StreakRecord | None, today: date) -> int:
    if not record or not record.last_increment_at:
        return 0
    if (today - record.last_increment_at.date()).days > 2:
        return 0
    return record.consecutive_days


def actions_in_window(
    actions: list,
    *,
    routine_action: str,
    since: datetime,
) -> list:
    return [
        a
        for a in actions
        if a.routine_action == routine_action and a.tapped_at >= since
    ]


def missed_yesterday(actions: list, routine_action: str, today: date) -> bool:
    yesterday = today - timedelta(days=1)
    for a in actions:
        if a.routine_action != routine_action:
            continue
        d = a.tapped_at.date()
        if d == yesterday:
            return False
    return any(a.routine_action == routine_action for a in actions)
