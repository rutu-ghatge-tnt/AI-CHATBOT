"""Per-day HLHP aggregates — retained for the last 30 days."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.core.local_date import calendar_date_key
from app.hlhp.core.bands import EnvironmentBands, bucketize_environment
from app.hlhp.core.sfi_driver import bands_snapshot, driver_key_from_env
from app.hlhp.models.environmental import EnvironmentalData

from app.hlhp.db import hl_db
from app.hlhp.db_errors import fail_write
from app.hlhp.mongo_setup import ensure_hlhp_indexes

logger = logging.getLogger(__name__)

_DAILY_LOG = "hlhp_daily_log"
RETENTION_DAYS = 30


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


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
    await ensure_hlhp_indexes()
    when = _parse_dt(scanned_at)
    date_key = calendar_date_key(when)
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
        env = EnvironmentalData(
            uv_index=float(uvi),
            temperature_c=float(temp_c),
            aqi=int(aqi),
            humidity_pct=float(rh_pct),
            location_name=city,
        )
        bands = bucketize_environment(env)
        doc.update(bands_snapshot(bands))
        doc["driver"] = driver_key_from_env(env)
        await col.update_one(
            {"user_id": user_id, "date": date_key},
            {"$set": doc},
            upsert=True,
        )
        await _prune_old(user_id)
    except Exception as exc:
        logger.warning("HLHP daily_log upsert failed for user=%s: %s", user_id, exc)


async def upsert_user_log_day(
    *,
    user_id: str,
    logged_at: datetime,
    outdoor_ok_score: Optional[int] = None,
    mood_verdict: str = "",
    sudden_event_tags: Optional[list[str]] = None,
    uvi: float = 0,
    temp_c: float = 0,
    aqi: int = 0,
    rh_pct: float = 0,
    city: str = "",
    bands: EnvironmentBands | None = None,
    driver: str | None = None,
    areas: Optional[list[str]] = None,
) -> None:
    """Record that the user saved today's log (feelings + streak tap)."""
    if not user_id:
        return
    await ensure_hlhp_indexes()
    when = _parse_dt(logged_at)
    date_key = calendar_date_key(when)
    tags = [str(t) for t in (sudden_event_tags or []) if t]
    col = hl_db[_DAILY_LOG]

    try:
        existing = await col.find_one({"user_id": user_id, "date": date_key})
        if existing:
            prev_count = int(existing.get("scan_count") or 1)
            prev_avg = existing.get("outdoor_score_avg")
            if outdoor_ok_score is not None:
                if prev_avg is not None:
                    count = prev_count + 1
                    avg = round((float(prev_avg) * prev_count + int(outdoor_ok_score)) / count, 1)
                else:
                    count = max(prev_count, 1)
                    avg = float(int(outdoor_ok_score))
            else:
                count = prev_count
                avg = float(prev_avg) if prev_avg is not None else None
            prior_tags = list(existing.get("sudden_event_tags") or [])
            merged_tags = list(dict.fromkeys(prior_tags + tags))
            mood = str(mood_verdict or existing.get("mood_verdict") or "")
        else:
            count = 1
            avg = float(int(outdoor_ok_score)) if outdoor_ok_score is not None else None
            merged_tags = tags
            mood = str(mood_verdict or "")

        doc: dict[str, Any] = {
            "user_id": user_id,
            "date": date_key,
            "scan_count": count,
            "mood_verdict": mood,
            "sudden_event_tags": merged_tags,
            "sudden_event": bool(merged_tags),
            "uvi": float(uvi if uvi else (existing or {}).get("uvi", 0)),
            "temp_c": float(temp_c if temp_c else (existing or {}).get("temp_c", 0)),
            "aqi": int(aqi if aqi else (existing or {}).get("aqi", 0)),
            "rh_pct": float(rh_pct if rh_pct else (existing or {}).get("rh_pct", 0)),
            "city": str(city or (existing or {}).get("city") or ""),
            "user_logged": True,
            "updated_at": datetime.now(timezone.utc),
        }
        if avg is not None:
            doc["outdoor_score_avg"] = avg
        if bands is not None:
            doc.update(bands_snapshot(bands))
        elif uvi or temp_c or aqi or rh_pct:
            env = EnvironmentalData(
                uv_index=float(uvi),
                temperature_c=float(temp_c),
                aqi=int(aqi),
                humidity_pct=float(rh_pct),
                location_name=city,
            )
            doc.update(bands_snapshot(bucketize_environment(env)))
        if driver:
            doc["driver"] = driver
        elif not existing or not existing.get("driver"):
            env = EnvironmentalData(
                uv_index=float(doc["uvi"]),
                temperature_c=float(doc["temp_c"]),
                aqi=int(doc["aqi"]),
                humidity_pct=float(doc["rh_pct"]),
                location_name=str(doc["city"]),
            )
            doc["driver"] = driver_key_from_env(env)
        if areas is not None:
            doc["areas"] = list(areas)

        await col.update_one(
            {"user_id": user_id, "date": date_key},
            {"$set": doc},
            upsert=True,
        )
        await _prune_old(user_id)
    except Exception as exc:
        fail_write(_DAILY_LOG, "upsert_user_log_day", exc)


async def fetch_daily_logs(
    user_id: str,
    *,
    since: datetime,
    limit: int = RETENTION_DAYS,
) -> list[dict[str, Any]]:
    if not user_id:
        return []
    await ensure_hlhp_indexes()
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
    await ensure_hlhp_indexes()
    by_day: dict[str, list[dict[str, Any]]] = {}
    for scan in scans:
        when = _parse_dt(scan.get("scanned_at"))
        by_day.setdefault(calendar_date_key(when), []).append(scan)

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
