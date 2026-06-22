"""WeatherAPI hourly slots for SFI timeline (history + forecast)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.hlhp.config import hl_settings
from app.hlhp.services.weatherapi_forecast import aqi_from_air_quality

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "hl:weatherapi:timeline"
SFI_SLOT_HOURS = (6, 9, 12, 15, 18, 21)


@dataclass(frozen=True)
class HourlyEnvReading:
    at_epoch: int
    local_time: str
    date: str
    slot_hour: int
    temp_c: float
    humidity_pct: float
    uv_index: float
    aqi: int
    source: str


def _to_float(value, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_hour(hours: list[dict], date_key: str, hour: int) -> dict | None:
    prefix = f"{date_key} {hour:02d}:"
    for row in hours:
        if not isinstance(row, dict):
            continue
        time_text = str(row.get("time") or "")
        if time_text.startswith(prefix):
            return row
    return None


def _hour_to_reading(
    hour_row: dict,
    *,
    date_key: str,
    slot_hour: int,
    source: str,
    fallback_aqi: int,
) -> HourlyEnvReading:
    aqi = aqi_from_air_quality(hour_row.get("air_quality"), fallback=fallback_aqi)
    return HourlyEnvReading(
        at_epoch=int(hour_row.get("time_epoch") or 0),
        local_time=str(hour_row.get("time") or ""),
        date=date_key,
        slot_hour=slot_hour,
        temp_c=round(_to_float(hour_row.get("temp_c"), 25.0), 1),
        humidity_pct=round(_to_float(hour_row.get("humidity"), 50.0), 1),
        uv_index=round(_to_float(hour_row.get("uv"), 0.0), 1),
        aqi=aqi,
        source=source,
    )


def extract_slot_readings(
    forecast_days: list[dict],
    *,
    source: str,
    allowed_dates: set[str] | None = None,
    fallback_aqi: int = 50,
) -> list[HourlyEnvReading]:
    readings: list[HourlyEnvReading] = []
    last_aqi = fallback_aqi

    for fd in forecast_days:
        if not isinstance(fd, dict):
            continue
        date_key = str(fd.get("date") or "")
        if not date_key:
            continue
        if allowed_dates is not None and date_key not in allowed_dates:
            continue
        hours = fd.get("hour") if isinstance(fd.get("hour"), list) else []
        for slot_hour in SFI_SLOT_HOURS:
            hour_row = _pick_hour(hours, date_key, slot_hour)
            if not hour_row:
                continue
            reading = _hour_to_reading(
                hour_row,
                date_key=date_key,
                slot_hour=slot_hour,
                source=source,
                fallback_aqi=last_aqi,
            )
            last_aqi = reading.aqi
            readings.append(reading)

    readings.sort(key=lambda r: r.at_epoch)
    return readings


def local_today(tz_id: str) -> date:
    try:
        return datetime.now(ZoneInfo(tz_id)).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def date_window(
    *,
    tz_id: str,
    days_back: int,
    days_ahead: int,
) -> tuple[date, set[str], set[str], set[str]]:
    """Return anchor today, all ISO dates, history dates, forecast dates."""
    today = local_today(tz_id)
    all_dates: set[str] = set()
    history_dates: set[str] = set()
    forecast_dates: set[str] = set()

    for offset in range(-days_back, days_ahead + 1):
        d = today + timedelta(days=offset)
        iso = d.isoformat()
        all_dates.add(iso)
        if offset < 0:
            history_dates.add(iso)
        else:
            forecast_dates.add(iso)

    return today, all_dates, history_dates, forecast_dates


async def _get_json(url: str, params: dict[str, Any]) -> dict | None:
    key = hl_settings.WEATHERAPI_KEY
    if not key:
        logger.warning("WEATHERAPI_KEY not set — SFI timeline unavailable")
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params={**params, "key": key, "aqi": "yes"})
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("WeatherAPI request failed (%s): %s", url, exc)
        return None


async def fetch_forecast_payload(
    latitude: float,
    longitude: float,
    *,
    days: int,
) -> dict | None:
    days = max(1, min(int(days), 14))
    return await _get_json(
        hl_settings.WEATHERAPI_FORECAST_URL,
        {"q": f"{latitude},{longitude}", "days": days},
    )


async def fetch_history_payload(
    latitude: float,
    longitude: float,
    *,
    start: date,
    end: date,
) -> dict | None:
    if start > end:
        return None
    return await _get_json(
        hl_settings.WEATHERAPI_HISTORY_URL,
        {
            "q": f"{latitude},{longitude}",
            "dt": start.isoformat(),
            "end_dt": end.isoformat(),
        },
    )


def _forecast_days(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    forecast = payload.get("forecast") if isinstance(payload.get("forecast"), dict) else {}
    days = forecast.get("forecastday")
    return [d for d in days if isinstance(d, dict)] if isinstance(days, list) else []


def _location_meta(payload: dict | None) -> tuple[str, str, float, float]:
    if not payload:
        return "Asia/Kolkata", "Unknown", 0.0, 0.0
    loc = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    tz_id = str(loc.get("tz_id") or "UTC")
    name = str(loc.get("name") or "Unknown")
    lat = _to_float(loc.get("lat"), 0.0)
    lon = _to_float(loc.get("lon"), 0.0)
    region = str(loc.get("region") or "")
    country = str(loc.get("country") or "")
    label = ", ".join(p for p in (name, region, country) if p) or [name]
    return tz_id, label, lat, lon


async def fetch_timeline_hourly_readings(
    latitude: float,
    longitude: float,
    *,
    days_back: int = 3,
    days_ahead: int = 3,
) -> tuple[list[HourlyEnvReading], str, str]:
    """
    Merge history + forecast hourly slot readings for the requested window.
    Returns (readings, timezone_id, location_name).
    """
    days_back = max(0, min(int(days_back), 7))
    days_ahead = max(0, min(int(days_ahead), 7))

    forecast_payload = await fetch_forecast_payload(
        latitude,
        longitude,
        days=max(1, days_ahead + 1),
    )
    tz_id, location_name, _, _ = _location_meta(forecast_payload)
    _, all_dates, history_dates, forecast_dates = date_window(
        tz_id=tz_id,
        days_back=days_back,
        days_ahead=days_ahead,
    )

    readings: list[HourlyEnvReading] = []
    fallback_aqi = 50
    current = (
        forecast_payload.get("current")
        if forecast_payload and isinstance(forecast_payload.get("current"), dict)
        else {}
    )
    if current:
        fallback_aqi = aqi_from_air_quality(current.get("air_quality"), fallback=fallback_aqi)

    if history_dates:
        start = min(date.fromisoformat(d) for d in history_dates)
        end = max(date.fromisoformat(d) for d in history_dates)
        history_payload = await fetch_history_payload(latitude, longitude, start=start, end=end)
        if history_payload:
            tz_id, location_name, _, _ = _location_meta(history_payload)
        readings.extend(
            extract_slot_readings(
                _forecast_days(history_payload),
                source="history",
                allowed_dates=history_dates,
                fallback_aqi=fallback_aqi,
            )
        )

    if forecast_dates:
        readings.extend(
            extract_slot_readings(
                _forecast_days(forecast_payload),
                source="forecast",
                allowed_dates=forecast_dates,
                fallback_aqi=fallback_aqi,
            )
        )

    # De-dupe same timestamp (today can appear in both payloads)
    by_epoch: dict[int, HourlyEnvReading] = {}
    for row in readings:
        if row.at_epoch <= 0:
            continue
        existing = by_epoch.get(row.at_epoch)
        if existing is None or (existing.source == "forecast" and row.source == "history"):
            by_epoch[row.at_epoch] = row

    merged = sorted(by_epoch.values(), key=lambda r: r.at_epoch)
    return merged, tz_id, location_name
