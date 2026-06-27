"""Per-day HLHP aggregates — retained for the last 15 days."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.db import hl_db

logger = logging.getLogger(__name__)

_DAILY_LOG = "hlhp_daily_log"
RETENTION_DAYS = 15
_INDEXEnsured = False


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


async def _ensure_indexes() -> None:
    global _INDEXEnsured
    if _INDEXEnsured:
        return
    try:
        col = hl_db[_DAILY_LOG]
        await col.create_index([("user_id", 1), ("date", -1)], unique=True)
        await col.create_index("updated_at")
        _INDEXEnsured = True
    except Exception as exc:
        logger.warning("HLHP daily_log index setup skipped: %s", exc)


async def _prune_old(user_id: str, *, keep_days: int = RETENTION_DAYS) -> None:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=keep_days)).isoformat()
    try:
        await hl_db[_DAILY_LOG].delete_many({"user_id": user_id, "date": {"$lt": cutoff}})
    except Exception as exc:
        logger.warning("HLHP daily_log prune failed for user=%s: %s", user_id, exc)


async def upsert_from_scan(
    *,
    user_id: str,
    scanned_at: datetime,
    outdoor_ok_score: int,
    mood_verdict: str,
    sudden_event_tags: list[str],
    uvi: float,
    temp_c: float,
    aqi: int,
    rh_pct: float,
    city: str,
) -> None:
    if not user_id:
        return
    await _ensure_indexes()
    when = _parse_dt(scanned_at)
    date_key = when.date().isoformat()
    tags = list(sudden_event_tags or [])
    col = hl_db[_DAILY_LOG]

    try:
        existing = await col.find_one({"user_id": user_id, "date": date_key})
        if existing:
            prev_count = int(existing.get("scan_count") or 1)
            prev_avg = float(existing.get("outdoor_score_avg") or existing.get("outdoor_ok_score") or 0)
            count = prev_count + 1
            avg = round((prev_avg * prev_count + int(outdoor_ok_score)) / count, 1)
            prior_tags = list(existing.get("sudden_event_tags") or [])
            merged_tags = list(dict.fromkeys(prior_tags + tags))
        else:
            count = 1
            avg = float(int(outdoor_ok_score))
            merged_tags = tags

        doc = {
            "user_id": user_id,
            "date": date_key,
            "outdoor_score_avg": avg,
            "scan_count": count,
            "mood_verdict": mood_verdict,
            "sudden_event_tags": merged_tags,
            "sudden_event": bool(merged_tags),
            "uvi": float(uvi),
            "temp_c": float(temp_c),
            "aqi": int(aqi),
            "rh_pct": float(rh_pct),
            "city": city,
            "updated_at": datetime.now(timezone.utc),
        }
        await col.update_one(
            {"user_id": user_id, "date": date_key},
            {"$set": doc},
            upsert=True,
        )
        await _prune_old(user_id)
    except Exception as exc:
        logger.warning("HLHP daily_log upsert failed for user=%s: %s", user_id, exc)


async def fetch_daily_logs(
    user_id: str,
    *,
    since: datetime,
    limit: int = RETENTION_DAYS,
) -> list[dict[str, Any]]:
    if not user_id:
        return []
    await _ensure_indexes()
    since_date = since.date().isoformat()
    try:
        cursor = (
            hl_db[_DAILY_LOG]
            .find({"user_id": user_id, "date": {"$gte": since_date}})
            .sort("date", -1)
            .limit(limit)
        )
        return [doc async for doc in cursor]
    except Exception as exc:
        logger.warning("HLHP daily_log fetch failed for user=%s: %s", user_id, exc)
        return []


async def backfill_from_scans(user_id: str, scans: list[dict[str, Any]]) -> None:
    """Rebuild daily aggregates from raw scan rows (migration / repair)."""
    if not user_id or not scans:
        return
    await _ensure_indexes()
    by_day: dict[str, list[dict[str, Any]]] = {}
    for scan in scans:
        when = _parse_dt(scan.get("scanned_at"))
        by_day.setdefault(when.date().isoformat(), []).append(scan)

    col = hl_db[_DAILY_LOG]
    for date_key, day_scans in by_day.items():
        scores = [int(s.get("outdoor_ok_score", 0)) for s in day_scans if s.get("outdoor_ok_score") is not None]
        if not scores:
            continue
        last = max(day_scans, key=lambda s: _parse_dt(s.get("scanned_at")))
        tags: list[str] = []
        for s in day_scans:
            tags.extend(s.get("sudden_event_tags") or [])
        merged_tags = list(dict.fromkeys(str(t) for t in tags if t))
        avg = round(sum(scores) / len(scores), 1)
        doc = {
            "user_id": user_id,
            "date": date_key,
            "outdoor_score_avg": avg,
            "scan_count": len(scores),
            "mood_verdict": str(last.get("mood_verdict") or ""),
            "sudden_event_tags": merged_tags,
            "sudden_event": bool(merged_tags),
            "uvi": float(last.get("uvi", 0)),
            "temp_c": float(last.get("temp_c", 0)),
            "aqi": int(last.get("aqi", 0)),
            "rh_pct": float(last.get("rh_pct", 0)),
            "city": str(last.get("city") or ""),
            "updated_at": datetime.now(timezone.utc),
        }
        try:
            await col.update_one(
                {"user_id": user_id, "date": date_key},
                {"$set": doc},
                upsert=True,
            )
        except Exception as exc:
            logger.warning("HLHP daily_log backfill failed for %s %s: %s", user_id, date_key, exc)
    await _prune_old(user_id)


def average_daily_scores(docs: list[dict[str, Any]]) -> Optional[float]:
    if not docs:
        return None
    vals = [float(d.get("outdoor_score_avg", 0)) for d in docs if d.get("outdoor_score_avg") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 1)
