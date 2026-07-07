"""Append-only HLHP feeling log sessions (symptoms + point-in-time environment snapshot)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.hlhp.db import hl_db
from app.hlhp.db_errors import fail_write
from app.hlhp.mongo_setup import ensure_hlhp_indexes

logger = logging.getLogger(__name__)

_LOG_EVENTS = "hlhp_user_log_events"
FEELING_LOG_COOLDOWN_HOURS = 5


class FeelingLogCooldownError(Exception):
    """Raised when a new feeling session is attempted before the cooldown elapses."""

    def __init__(self, *, next_log_at: datetime, retry_after_seconds: int) -> None:
        self.next_log_at = next_log_at
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Feeling log cooldown until {next_log_at.isoformat()}")


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def feeling_log_cooldown_remaining(
    last_committed_at: datetime | None,
    at: datetime,
) -> int | None:
    """Seconds until the next feeling log is allowed, or None if logging is allowed now."""
    if last_committed_at is None:
        return None
    when = _parse_dt(at)
    last = _parse_dt(last_committed_at)
    elapsed = (when - last).total_seconds()
    cooldown_sec = FEELING_LOG_COOLDOWN_HOURS * 3600
    if elapsed >= cooldown_sec:
        return None
    return int(cooldown_sec - elapsed)


def next_feeling_log_at(last_committed_at: datetime,) -> datetime:
    return _parse_dt(last_committed_at) + timedelta(hours=FEELING_LOG_COOLDOWN_HOURS)


def assert_feeling_log_allowed(
    last_committed_at: datetime | None,
    at: datetime,
) -> None:
    remaining = feeling_log_cooldown_remaining(last_committed_at, at)
    if remaining is None:
        return
    last = _parse_dt(last_committed_at)  # type: ignore[arg-type]
    raise FeelingLogCooldownError(
        next_log_at=next_feeling_log_at(last),
        retry_after_seconds=remaining,
    )


async def fetch_latest_log_session(user_id: str) -> dict[str, Any] | None:
    """Most recent committed feeling session for the user."""
    if not user_id:
        return None
    await ensure_hlhp_indexes()
    try:
        return await hl_db[_LOG_EVENTS].find_one(
            {"user_id": user_id},
            sort=[("ts", -1)],
        )
    except Exception as exc:
        logger.warning("HLHP user_log_events latest session fetch failed: %s", exc)
        return None


async def fetch_feeling_log_status(user_id: str, *, at: datetime | None = None) -> dict[str, Any]:
    """Whether the user can commit a new feeling session right now."""
    when = _parse_dt(at) if at is not None else datetime.now(timezone.utc)
    latest = await fetch_latest_log_session(user_id)
    last_ts = _parse_dt(latest["ts"]) if latest and latest.get("ts") else None
    remaining = feeling_log_cooldown_remaining(last_ts, when)
    can_log = remaining is None
    next_at = None if can_log or last_ts is None else next_feeling_log_at(last_ts)
    return {
        "can_log": can_log,
        "cooldown_hours": FEELING_LOG_COOLDOWN_HOURS,
        "next_log_at": next_at.isoformat() if next_at is not None else None,
        "retry_after_seconds": remaining,
    }


async def insert_log_event(doc: dict[str, Any]) -> str:
    """Persist one immutable feeling session; returns session_id."""
    if not doc.get("user_id"):
        return ""
    await ensure_hlhp_indexes()
    session_id = str(doc.get("session_id") or uuid.uuid4())
    payload = {**doc, "session_id": session_id}
    try:
        await hl_db[_LOG_EVENTS].insert_one(payload)
    except Exception as exc:
        fail_write(_LOG_EVENTS, "insert", exc)
    return session_id


async def fetch_log_events(
    user_id: str,
    *,
    since: datetime | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    if not user_id:
        return []
    await ensure_hlhp_indexes()
    query: dict[str, Any] = {"user_id": user_id}
    if since is not None:
        query["ts"] = {"$gte": _parse_dt(since)}
    out: list[dict[str, Any]] = []
    try:
        cursor = hl_db[_LOG_EVENTS].find(query).sort("ts", 1).limit(limit)
        async for doc in cursor:
            out.append(doc)
    except Exception as exc:
        logger.warning("HLHP user_log_events fetch failed: %s", exc)
    return out


async def fetch_latest_log_for_date(user_id: str, date_key: str) -> dict[str, Any] | None:
    """Most recent feeling session for a calendar day (symptoms + areas)."""
    if not user_id or not date_key:
        return None
    await ensure_hlhp_indexes()
    try:
        return await hl_db[_LOG_EVENTS].find_one(
            {"user_id": user_id, "date": date_key},
            sort=[("ts", -1)],
        )
    except Exception as exc:
        logger.warning("HLHP user_log_events latest fetch failed: %s", exc)
        return None


async def fetch_log_event_dates(user_id: str, *, limit: int = 400) -> set[str]:
    if not user_id:
        return set()
    await ensure_hlhp_indexes()
    dates: set[str] = set()
    try:
        cursor = (
            hl_db[_LOG_EVENTS]
            .find({"user_id": user_id}, {"date": 1})
            .sort("ts", -1)
            .limit(limit)
        )
        async for doc in cursor:
            day = str(doc.get("date") or "")
            if day:
                dates.add(day)
    except Exception as exc:
        logger.warning("HLHP user_log_events fetch failed: %s", exc)
    return dates


async def count_log_events(user_id: str) -> int:
    if not user_id:
        return 0
    await ensure_hlhp_indexes()
    try:
        return await hl_db[_LOG_EVENTS].count_documents({"user_id": user_id})
    except Exception as exc:
        logger.warning("HLHP user_log_events count failed: %s", exc)
        return 0
