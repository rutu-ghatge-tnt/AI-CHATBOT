"""Per-day HLHP aggregates — retained for the last 30 days."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.core.local_date import calendar_date_key
from app.hlhp.core.bands import EnvironmentBands, bucketize_environment
from app.hlhp.core.sfi_driver import bands_snapshot, driver_key_for_day
from app.hlhp.models.environmental import EnvironmentalData

from app.hlhp.db import hl_db
from app.hlhp.db_errors import fail_write
from app.hlhp.mongo_setup import ensure_hlhp_indexes

logger = logging.getLogger(__name__)

_DAILY_LOG = "hlhp_daily_log"
RETENTION_DAYS = 30


def _avg_env_readings(
    existing: dict[str, Any] | None,
    prev_count: int,
    *,
    uvi: float,
    temp_c: float,
    aqi: int,
    rh_pct: float,
) -> tuple[float, float, int, float]:
    """Running mean of env readings across scans on the same calendar day."""
    if not existing or prev_count <= 0:
        return float(uvi), float(temp_c), int(aqi), float(rh_pct)
    n = float(prev_count)
    return (
        round((float(existing.get("uvi", uvi)) * n + float(uvi)) / (n + 1), 2),
        round((float(existing.get("temp_c", temp_c)) * n + float(temp_c)) / (n + 1), 2),
        int(round((int(existing.get("aqi", aqi)) * n + int(aqi)) / (n + 1))),
        round((float(existing.get("rh_pct", rh_pct)) * n + float(rh_pct)) / (n + 1), 2),
    )


def _apply_day_driver(doc: dict[str, Any]) -> None:
    """Set bands + recap driver from daily SFI average and day-mean env."""
    city = str(doc.get("city") or "")
    env = EnvironmentalData(
        uv_index=float(doc.get("uvi", 0)),
        temperature_c=float(doc.get("temp_c", 0)),
        aqi=int(doc.get("aqi", 0)),
        humidity_pct=float(doc.get("rh_pct", 0)),
        location_name=city,
    )
    doc.update(bands_snapshot(bucketize_environment(env)))
    avg = doc.get("outdoor_score_avg")
    driver = driver_key_for_day(
        outdoor_score_avg=float(avg) if avg is not None else None,
        env=env,
    )
    if driver is not None:
        doc["driver"] = driver
    else:
        doc.pop("driver", None)


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
            avg_uvi, avg_temp, avg_aqi, avg_rh = _avg_env_readings(
                existing,
                prev_count,
                uvi=uvi,
                temp_c=temp_c,
                aqi=aqi,
                rh_pct=rh_pct,
            )
            prior_tags = list(existing.get("sudden_event_tags") or [])
            merged_tags = list(dict.fromkeys(prior_tags + tags))
        else:
            count = 1
            avg = float(int(outdoor_ok_score))
            avg_uvi, avg_temp, avg_aqi, avg_rh = float(uvi), float(temp_c), int(aqi), float(rh_pct)
            merged_tags = tags

        doc = {
            "user_id": user_id,
            "date": date_key,
            "outdoor_score_avg": avg,
            "scan_count": count,
            "mood_verdict": mood_verdict,
            "sudden_event_tags": merged_tags,
            "sudden_event": bool(merged_tags),
            "uvi": avg_uvi,
            "temp_c": avg_temp,
            "aqi": avg_aqi,
            "rh_pct": avg_rh,
            "city": city,
            "updated_at": datetime.now(timezone.utc),
        }
        _apply_day_driver(doc)
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
            has_new_env = bool(uvi or temp_c or aqi or rh_pct)
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

            if has_new_env and outdoor_ok_score is not None:
                avg_uvi, avg_temp, avg_aqi, avg_rh = _avg_env_readings(
                    existing,
                    prev_count if prev_avg is not None else max(prev_count - 1, 0),
                    uvi=uvi,
                    temp_c=temp_c,
                    aqi=aqi,
                    rh_pct=rh_pct,
                )
            else:
                avg_uvi = float(uvi if uvi else existing.get("uvi", 0))
                avg_temp = float(temp_c if temp_c else existing.get("temp_c", 0))
                avg_aqi = int(aqi if aqi else existing.get("aqi", 0))
                avg_rh = float(rh_pct if rh_pct else existing.get("rh_pct", 0))

            prior_tags = list(existing.get("sudden_event_tags") or [])
            merged_tags = list(dict.fromkeys(prior_tags + tags))
            mood = str(mood_verdict or existing.get("mood_verdict") or "")
        else:
            count = 1
            avg = float(int(outdoor_ok_score)) if outdoor_ok_score is not None else None
            avg_uvi, avg_temp, avg_aqi, avg_rh = float(uvi), float(temp_c), int(aqi), float(rh_pct)
            merged_tags = tags
            mood = str(mood_verdict or "")

        doc: dict[str, Any] = {
            "user_id": user_id,
            "date": date_key,
            "scan_count": count,
            "mood_verdict": mood,
            "sudden_event_tags": merged_tags,
            "sudden_event": bool(merged_tags),
            "uvi": avg_uvi,
            "temp_c": avg_temp,
            "aqi": avg_aqi,
            "rh_pct": avg_rh,
            "city": str(city or (existing or {}).get("city") or ""),
            "user_logged": True,
            "updated_at": datetime.now(timezone.utc),
        }
        if avg is not None:
            doc["outdoor_score_avg"] = avg
        if bands is not None:
            doc.update(bands_snapshot(bands))
        _apply_day_driver(doc)
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
        n = len(day_scans)
        avg_uvi = round(sum(float(s.get("uvi", 0)) for s in day_scans) / n, 2)
        avg_temp = round(sum(float(s.get("temp_c", 0)) for s in day_scans) / n, 2)
        avg_aqi = int(round(sum(int(s.get("aqi", 0)) for s in day_scans) / n))
        avg_rh = round(sum(float(s.get("rh_pct", 0)) for s in day_scans) / n, 2)
        doc = {
            "user_id": user_id,
            "date": date_key,
            "outdoor_score_avg": avg,
            "scan_count": len(scores),
            "mood_verdict": str(last.get("mood_verdict") or ""),
            "sudden_event_tags": merged_tags,
            "sudden_event": bool(merged_tags),
            "uvi": avg_uvi,
            "temp_c": avg_temp,
            "aqi": avg_aqi,
            "rh_pct": avg_rh,
            "city": str(last.get("city") or ""),
            "updated_at": datetime.now(timezone.utc),
        }
        _apply_day_driver(doc)
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
