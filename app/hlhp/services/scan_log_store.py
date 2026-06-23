"""Persist HLHP scan results for history, delta baseline, and catch-up."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.db import hl_db

logger = logging.getLogger(__name__)

_SCAN_LOG = "hlhp_scan_log"
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
        col = hl_db[_SCAN_LOG]
        await col.create_index([("user_id", 1), ("scanned_at", -1)])
        await col.create_index("scanned_at")
        _INDEXEnsured = True
    except Exception as exc:
        logger.warning("HLHP scan_log index setup skipped: %s", exc)


async def record_scan_log(
    *,
    user_id: str,
    scanned_at: datetime,
    city: str,
    mode: str,
    outdoor_ok_score: int,
    mood_verdict: str,
    sudden_event_tags: list[str],
    uvi: float,
    temp_c: float,
    aqi: int,
    rh_pct: float,
    alert_rule_ids: list[str],
    concern_id: Optional[str] = None,
    snapshot_version: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> None:
    if not user_id:
        return
    await _ensure_indexes()
    doc = {
        "user_id": user_id,
        "scanned_at": _parse_dt(scanned_at),
        "city": city,
        "mode": mode,
        "outdoor_ok_score": int(outdoor_ok_score),
        "mood_verdict": mood_verdict,
        "sudden_event_tags": list(sudden_event_tags or []),
        "uvi": float(uvi),
        "temp_c": float(temp_c),
        "aqi": int(aqi),
        "rh_pct": float(rh_pct),
        "alert_rule_ids": list(alert_rule_ids or []),
        "concern_id": concern_id,
        "snapshot_version": snapshot_version,
        "latitude": latitude,
        "longitude": longitude,
    }
    try:
        await hl_db[_SCAN_LOG].insert_one(doc)
        from app.hlhp.services.daily_log_store import upsert_from_scan

        await upsert_from_scan(
            user_id=user_id,
            scanned_at=doc["scanned_at"],
            outdoor_ok_score=doc["outdoor_ok_score"],
            mood_verdict=doc["mood_verdict"],
            sudden_event_tags=doc["sudden_event_tags"],
            uvi=doc["uvi"],
            temp_c=doc["temp_c"],
            aqi=doc["aqi"],
            rh_pct=doc["rh_pct"],
            city=doc["city"],
        )
    except Exception as exc:
        logger.warning("HLHP scan_log insert failed for user=%s: %s", user_id, exc)


async def fetch_scans(user_id: str, *, since: datetime, limit: int = 500) -> list[dict[str, Any]]:
    if not user_id:
        return []
    try:
        cursor = (
            hl_db[_SCAN_LOG]
            .find({"user_id": user_id, "scanned_at": {"$gte": since}})
            .sort("scanned_at", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]
    except Exception as exc:
        logger.warning("HLHP scan_log fetch failed for user=%s: %s", user_id, exc)
        return []


async def scan_gap_days(user_id: str) -> Optional[int]:
    """Days between the two most recent scans (for returner banner)."""
    if not user_id:
        return None
    try:
        cursor = (
            hl_db[_SCAN_LOG]
            .find({"user_id": user_id}, projection={"scanned_at": 1})
            .sort("scanned_at", -1)
            .limit(2)
        )
        docs = [doc async for doc in cursor]
        if len(docs) < 2:
            return None
        latest = _parse_dt(docs[0]["scanned_at"])
        prior = _parse_dt(docs[1]["scanned_at"])
        return max(0, (latest.date() - prior.date()).days)
    except Exception as exc:
        logger.warning("HLHP scan_gap_days failed: %s", exc)
        return None


async def last_scan_at(user_id: str) -> Optional[datetime]:
    if not user_id:
        return None
    try:
        doc = await hl_db[_SCAN_LOG].find_one(
            {"user_id": user_id},
            sort=[("scanned_at", -1)],
            projection={"scanned_at": 1},
        )
        if doc and doc.get("scanned_at"):
            return _parse_dt(doc["scanned_at"])
    except Exception as exc:
        logger.warning("HLHP last_scan_at failed: %s", exc)
    return None


async def env_baseline_7d(user_id: str, *, before: datetime) -> Optional[dict[str, float]]:
    """Rolling 7-day env averages strictly before `before` (for delta detection)."""
    if not user_id:
        return None
    window_start = before - timedelta(days=7)
    scans = await fetch_scans(user_id, since=window_start, limit=200)
    scans = [s for s in scans if _parse_dt(s.get("scanned_at")) < _parse_dt(before)]
    if not scans:
        return None
    n = len(scans)
    return {
        "uvi_avg": sum(float(s.get("uvi", 0)) for s in scans) / n,
        "temp_avg": sum(float(s.get("temp_c", 0)) for s in scans) / n,
        "aqi_avg": sum(int(s.get("aqi", 0)) for s in scans) / n,
        "rh_avg": sum(float(s.get("rh_pct", 0)) for s in scans) / n,
    }
