"""Collect city weather + V4 SFI into permanent daily/slot archives.

Non-PII. IST calendar dates. Idempotent upserts. Chart path and CLI jobs share this.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.sfi_driver import bands_snapshot
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.city_env_store import (
    CITY_ENV_TZ,
    SCORING_VERSION,
    city_key_from_label,
    upsert_city_env_daily,
    upsert_city_env_slot,
)
from app.hlhp.services.sfi_unified import resolve_sfi
from app.hlhp.services.weatherapi_forecast import aqi_from_air_quality
from app.hlhp.services.weatherapi_timeline import SFI_SLOT_HOURS

logger = logging.getLogger(__name__)

_IST = ZoneInfo(CITY_ENV_TZ)
_SOURCE = "weatherapi_slot_avg"


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _library_version() -> str:
    try:
        return str(get_scenario_store().version or "3.6")
    except Exception:
        return "3.6"


def _pick_hour(hours: list[dict], date_iso: str, hour: int) -> dict | None:
    prefix = f"{date_iso} {hour:02d}:"
    for row in hours:
        if isinstance(row, dict) and str(row.get("time") or "").startswith(prefix):
            return row
    return None


def _day_row_from_payload(data: dict[str, Any], date_iso: str) -> dict[str, Any] | None:
    forecast = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
    days = forecast.get("forecastday") if isinstance(forecast.get("forecastday"), list) else []
    for fd in days:
        if isinstance(fd, dict) and str(fd.get("date") or "") == date_iso:
            return fd
    if days and isinstance(days[0], dict):
        return days[0]
    return None


def extract_slot_metrics(
    data: dict[str, Any] | None,
    date_iso: str,
) -> list[dict[str, Any]]:
    """Pull SFI_SLOT_HOURS samples from a WeatherAPI forecast/history payload."""
    if not isinstance(data, dict):
        return []
    day_row = _day_row_from_payload(data, date_iso)
    if not isinstance(day_row, dict):
        return []
    hours = day_row.get("hour") if isinstance(day_row.get("hour"), list) else []
    out: list[dict[str, Any]] = []
    for slot in SFI_SLOT_HOURS:
        hour_row = _pick_hour(hours, date_iso, slot)
        if not isinstance(hour_row, dict):
            continue
        out.append(
            {
                "slot_hour": int(slot),
                "temperature_c": round(_to_float(hour_row.get("temp_c"), 25.0), 1),
                "humidity_pct": round(_to_float(hour_row.get("humidity"), 50.0), 1),
                "uv_index": round(_to_float(hour_row.get("uv"), 5.0), 1),
                "aqi": int(aqi_from_air_quality(hour_row.get("air_quality"), fallback=50)),
                "wind_kmh": round(_to_float(hour_row.get("wind_kph"), 0.0), 1),
            }
        )
    return out


def average_slot_metrics(slots: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not slots:
        return None
    n = float(len(slots))
    return {
        "temperature_c": round(sum(float(s["temperature_c"]) for s in slots) / n, 1),
        "humidity_pct": round(sum(float(s["humidity_pct"]) for s in slots) / n, 1),
        "uv_index": round(sum(float(s["uv_index"]) for s in slots) / n, 1),
        "aqi": int(round(sum(int(s["aqi"]) for s in slots) / n)),
        "wind_kmh": round(sum(float(s["wind_kmh"]) for s in slots) / n, 1),
        "slots_count": len(slots),
    }


def _score_metrics(city_label: str, metrics: dict[str, Any]) -> dict[str, Any]:
    env = EnvironmentalData(
        uv_index=float(metrics["uv_index"]),
        temperature_c=float(metrics["temperature_c"]),
        aqi=int(metrics["aqi"]),
        humidity_pct=float(metrics["humidity_pct"]),
        wind_kmh=float(metrics.get("wind_kmh") or 0.0),
        location_name=city_label,
    )
    eval_ = resolve_sfi(env, None, guest_mode=True, surge=False)
    bands = bands_snapshot(bucketize_environment(env))
    return {
        "sfi_env": int(eval_.environmental_sfi),
        "mode": eval_.mode,
        "dominant_driver": eval_.dominant_factor,
        **bands,
    }


def _base_meta(
    *,
    city_label: str,
    on_board: bool,
    query: str,
    date_iso: str,
) -> dict[str, Any]:
    return {
        "city_key": city_key_from_label(city_label),
        "city_label": city_label,
        "on_board": bool(on_board),
        "date": date_iso,
        "tz": CITY_ENV_TZ,
        "query": query,
        "source": _SOURCE,
        "scoring_version": SCORING_VERSION,
        "library_version": _library_version(),
        "fetched_at": datetime.now(timezone.utc),
    }


async def persist_city_env_from_payload(
    *,
    city_label: str,
    query: str,
    date_iso: str,
    payload: dict[str, Any] | None,
    on_board: bool,
    yesterday_sfi: int | None = None,
) -> dict[str, Any]:
    """Extract slots → upsert slot + daily rows. Returns summary for callers/jobs."""
    slots = extract_slot_metrics(payload, date_iso)
    meta = _base_meta(
        city_label=city_label, on_board=on_board, query=query, date_iso=date_iso
    )
    if not slots:
        # No clutter: skip empty rows; absence means "not collected".
        return {"city": city_label, "date": date_iso, "ok": False, "slots": 0}

    scored_slots: list[dict[str, Any]] = []
    for sample in slots:
        scored = _score_metrics(city_label, sample)
        slot_doc = {
            **meta,
            **sample,
            **scored,
            "ok": True,
        }
        await upsert_city_env_slot(slot_doc)
        scored_slots.append({**sample, **scored})

    day_avg = average_slot_metrics(slots)
    assert day_avg is not None
    day_score = _score_metrics(city_label, day_avg)
    daily_doc: dict[str, Any] = {
        **meta,
        **day_avg,
        **day_score,
        "ok": True,
        "partial": len(slots) < len(SFI_SLOT_HOURS),
    }
    if yesterday_sfi is not None:
        daily_doc["yesterday_sfi"] = int(yesterday_sfi)
        daily_doc["delta"] = int(day_score["sfi_env"]) - int(yesterday_sfi)
    await upsert_city_env_daily(daily_doc)
    return {
        "city": city_label,
        "date": date_iso,
        "ok": True,
        "slots": len(slots),
        "sfi_env": day_score["sfi_env"],
    }


async def persist_city_env_day_pair(
    *,
    city_label: str,
    query: str,
    today_iso: str,
    yesterday_iso: str,
    today_payload: dict[str, Any] | None,
    yesterday_payload: dict[str, Any] | None,
    on_board: bool,
) -> dict[str, Any]:
    """Persist yesterday then today so today's delta can use yesterday's SFI."""
    y_summary = await persist_city_env_from_payload(
        city_label=city_label,
        query=query,
        date_iso=yesterday_iso,
        payload=yesterday_payload,
        on_board=on_board,
    )
    y_sfi = y_summary.get("sfi_env") if y_summary.get("ok") else None
    t_summary = await persist_city_env_from_payload(
        city_label=city_label,
        query=query,
        date_iso=today_iso,
        payload=today_payload,
        on_board=on_board,
        yesterday_sfi=int(y_sfi) if y_sfi is not None else None,
    )
    return {"yesterday": y_summary, "today": t_summary}


def ist_today_yesterday() -> tuple[str, str]:
    today = datetime.now(_IST).date()
    return today.isoformat(), (today - timedelta(days=1)).isoformat()


def iter_ist_dates(date_from: date, date_to: date) -> list[str]:
    if date_to < date_from:
        return []
    out: list[str] = []
    cur = date_from
    while cur <= date_to:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out
