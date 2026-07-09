"""Pre-unlock nudges + weekly digest scheduling for Patterns v2."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app.hlhp.patterns.hlhp_patterns_engine import Config, Pattern, PatternState
from app.hlhp.patterns.hlhp_patterns_prompts import lifecycle
from app.hlhp.services.pattern_state_store import get_pattern_state, save_pattern_state
from app.hlhp.services.patterns_lifecycle_service import enqueue_notifications
from app.hlhp.services.patterns_narration_service import refresh_weekly_digest

logger = logging.getLogger(__name__)


def _days_since(ts: datetime | None, today: date) -> int | None:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        d = ts.date() if ts.tzinfo else ts.replace(tzinfo=timezone.utc).date()
    else:
        return None
    return (today - d).days


async def maybe_enqueue_behind_pace_nudge(
    user_id: str,
    ps: PatternState,
    *,
    today: date,
) -> bool:
    """Max 1 behind-pace push per week for pre-unlock users still short of 25 log-days."""
    if ps.unlocked_at is not None:
        return False
    if ps.state not in ("LOCKED", "EARLY_SIGNALS"):
        return False
    remaining = max(0, Config.UNLOCK_LOG_DAYS - ps.log_days_30)
    if remaining <= 0:
        return False

    since = _days_since(getattr(ps, "last_behind_pace_push_at", None), today)
    if since is not None and since < 7:
        return False

    copy = lifecycle("behind.push", remaining=remaining)
    await enqueue_notifications(
        [
            {
                "user_id": user_id,
                "kind": "push_behind",
                "copy": copy,
                "remaining_logs": remaining,
            }
        ]
    )
    ps.last_behind_pace_push_at = datetime.now(timezone.utc)
    await save_pattern_state(ps)
    return True


async def maybe_refresh_weekly_digest(
    user_id: str,
    ps: PatternState,
    patterns: list[Pattern],
    profile: dict,
    *,
    today: date,
) -> bool:
    """ACTIVE users only; Sunday local; at most once per 7 days."""
    if ps.state != "UNLOCKED_ACTIVE":
        return False
    if today.weekday() != 6:
        return False

    since = _days_since(getattr(ps, "last_weekly_digest_at", None), today)
    if since is not None and since < 7:
        return False

    try:
        await refresh_weekly_digest(user_id, ps, patterns, profile)
    except Exception as exc:
        logger.warning("weekly digest failed user=%s: %s", user_id, exc)
        return False

    ps.last_weekly_digest_at = datetime.now(timezone.utc)
    await save_pattern_state(ps)

    from app.hlhp.services.pattern_state_store import get_narration_cache

    cache = await get_narration_cache(user_id)
    digest_copy = cache.get("weekly_digest") or lifecycle("active.digest")
    await enqueue_notifications(
        [
            {
                "user_id": user_id,
                "kind": "weekly_digest",
                "copy": digest_copy,
            }
        ]
    )
    return True


async def maybe_enqueue_day2_push(
    user_id: str,
    ps: PatternState,
    *,
    today: date,
) -> bool:
    """One-time day-2 locked push (spec §6.1)."""
    if ps.unlocked_at is not None:
        return False
    if ps.first_log_date is None:
        return False
    days_on_track = (today - ps.first_log_date).days
    if days_on_track < 1:
        return False
    if getattr(ps, "last_locked_push_d2_at", None) is not None:
        return False
    if ps.log_days_30 < 2:
        return False

    copy = lifecycle("locked.push_d2")
    await enqueue_notifications(
        [
            {
                "user_id": user_id,
                "kind": "push_d2",
                "copy": copy,
            }
        ]
    )
    ps.last_locked_push_d2_at = datetime.now(timezone.utc)
    await save_pattern_state(ps)
    return True


async def run_nudges_for_user(
    user_id: str,
    *,
    today: date | None = None,
    patterns: list[Pattern] | None = None,
    profile: dict | None = None,
) -> dict[str, bool]:
    """Called after each patterns recompute (log save or patterns tab fetch)."""
    from app.hlhp.core.local_date import today_local

    today = today or today_local()
    ps = await get_pattern_state(user_id)
    behind = await maybe_enqueue_behind_pace_nudge(user_id, ps, today=today)
    ps = await get_pattern_state(user_id)
    day2 = await maybe_enqueue_day2_push(user_id, ps, today=today)
    weekly = False
    if patterns is not None and profile is not None:
        ps = await get_pattern_state(user_id)
        weekly = await maybe_refresh_weekly_digest(
            user_id, ps, patterns, profile, today=today
        )
    return {"behind_pace": behind, "day2_push": day2, "weekly_digest": weekly}
