"""Open-Meteo CAMS UV — single HLHP source for uv_index.

WeatherAPI remains the source for temp / humidity / AQI / wind.
On Open-Meteo failure, callers keep WeatherAPI UV (no hard break).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from app.hlhp.config import hl_settings
from app.hlhp.services.weather_http import get_json
from app.hlhp.services.weather_quota import PROVIDER_OPEN_METEO
from app.hlhp.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_CURRENT = "hl:openmeteo:uv:current"
_CACHE_HOURLY = "hl:openmeteo:uv:hourly"
_CACHE_DAILY = "hl:openmeteo:uv:daily"
SOURCE = "open_meteo"


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def coords_from_weatherapi_payload(payload: dict | None) -> tuple[float, float] | None:
    if not isinstance(payload, dict):
        return None
    loc = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    lat = _to_float(loc.get("lat"))
    lon = _to_float(loc.get("lon"))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def _round_coord(value: float) -> float:
    return round(float(value), 2)


async def _get_json(url: str, params: dict[str, Any]) -> dict | None:
    return await get_json(
        url, params=params, timeout=12, provider=PROVIDER_OPEN_METEO
    )

def _parse_hourly_uv(data: dict) -> dict[tuple[str, int], float]:
    hourly = data.get("hourly") if isinstance(data.get("hourly"), dict) else {}
    times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    values = hourly.get("uv_index") if isinstance(hourly.get("uv_index"), list) else []
    out: dict[tuple[str, int], float] = {}
    for i, raw_t in enumerate(times):
        if i >= len(values):
            break
        uv = _to_float(values[i])
        if uv is None:
            continue
        text = str(raw_t or "")
        # "2026-07-24T14:00" or "2026-07-24T14:00:00"
        if "T" not in text:
            continue
        date_part, _, time_part = text.partition("T")
        hour_txt = time_part[:2]
        try:
            hour = int(hour_txt)
        except ValueError:
            continue
        if not date_part or not (0 <= hour <= 23):
            continue
        out[(date_part, hour)] = round(max(0.0, uv), 1)
    return out


def _local_now(tz_id: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(tz_id))
    except Exception:
        return datetime.now(timezone.utc)


async def fetch_hourly_uv_map(
    latitude: float,
    longitude: float,
    *,
    start: date,
    end: date,
    timezone_id: str = "auto",
) -> dict[tuple[str, int], float]:
    """Return {(YYYY-MM-DD, hour): uv_index} from CAMS air-quality hourly."""
    if end < start:
        return {}

    cache_key = (
        f"{_CACHE_HOURLY}:{_round_coord(latitude)}:{_round_coord(longitude)}"
        f":{start.isoformat()}:{end.isoformat()}:{timezone_id}"
    )
    cached = await get_cached(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("map"), dict):
        parsed: dict[tuple[str, int], float] = {}
        for key, value in cached["map"].items():
            if not isinstance(key, str) or "|" not in key:
                continue
            d, _, h = key.partition("|")
            try:
                parsed[(d, int(h))] = float(value)
            except (TypeError, ValueError):
                continue
        if parsed:
            return parsed

    data = await _get_json(
        _AIR_QUALITY_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "uv_index",
            "timezone": timezone_id or "auto",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    if not data:
        return {}

    uv_map = _parse_hourly_uv(data)
    if uv_map:
        serial = {f"{d}|{h}": uv for (d, h), uv in uv_map.items()}
        await set_cached(cache_key, {"map": serial}, hl_settings.WEATHER_CACHE_TTL)
    return uv_map


async def fetch_current_uv(
    latitude: float,
    longitude: float,
    *,
    timezone_id: str = "auto",
) -> float | None:
    """Nearest local-hour CAMS uv_index for this location."""
    cache_key = f"{_CACHE_CURRENT}:{_round_coord(latitude)}:{_round_coord(longitude)}"
    cached = await get_cached(cache_key)
    if isinstance(cached, dict) and cached.get("uv_index") is not None:
        return _to_float(cached["uv_index"])

    data = await _get_json(
        _AIR_QUALITY_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "uv_index",
            "timezone": timezone_id or "auto",
            "forecast_days": 1,
        },
    )
    if not data:
        return None

    uv_map = _parse_hourly_uv(data)
    if not uv_map:
        return None

    tz_name = str(data.get("timezone") or "UTC")
    now = _local_now(tz_name)
    now_naive = now.replace(tzinfo=None)
    best: float | None = None
    best_delta: int | None = None
    for (d, h), uv in uv_map.items():
        try:
            dt = datetime.fromisoformat(f"{d}T{h:02d}:00")
        except ValueError:
            continue
        delta = abs(int((dt - now_naive).total_seconds() // 3600))
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best = uv

    if best is None:
        return None

    await set_cached(cache_key, {"uv_index": best}, hl_settings.WEATHER_CACHE_TTL)
    return best

async def fetch_daily_uv_max(
    latitude: float,
    longitude: float,
    *,
    days: int = 3,
    timezone_id: str = "auto",
) -> dict[str, float]:
    """Map YYYY-MM-DD → daily uv_index_max (forecast API)."""
    days = max(1, min(int(days), 16))
    cache_key = (
        f"{_CACHE_DAILY}:{_round_coord(latitude)}:{_round_coord(longitude)}"
        f":{days}:{timezone_id}"
    )
    cached = await get_cached(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("by_date"), dict):
        out = {
            str(k): float(v)
            for k, v in cached["by_date"].items()
            if _to_float(v) is not None
        }
        if out:
            return out

    data = await _get_json(
        _FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "uv_index_max",
            "timezone": timezone_id or "auto",
            "forecast_days": days,
        },
    )
    if not data:
        return {}

    daily = data.get("daily") if isinstance(data.get("daily"), dict) else {}
    dates = daily.get("time") if isinstance(daily.get("time"), list) else []
    values = daily.get("uv_index_max") if isinstance(daily.get("uv_index_max"), list) else []
    by_date: dict[str, float] = {}
    for i, d in enumerate(dates):
        if i >= len(values):
            break
        uv = _to_float(values[i])
        if uv is None:
            continue
        by_date[str(d)] = round(max(0.0, uv), 1)

    if by_date:
        await set_cached(
            cache_key,
            {"by_date": by_date},
            hl_settings.FORECAST_CACHE_TTL,
        )
    return by_date


def slot_uv_average(
    uv_map: dict[tuple[str, int], float],
    date_iso: str,
    hours: Iterable[int],
) -> float | None:
    samples = [uv_map[(date_iso, h)] for h in hours if (date_iso, h) in uv_map]
    if not samples:
        return None
    return round(sum(samples) / len(samples), 1)


def apply_hourly_uv(
    readings: list[Any],
    uv_map: dict[tuple[str, int], float],
    *,
    date_attr: str = "date",
    hour_attr: str = "slot_hour",
    uv_attr: str = "uv_index",
) -> tuple[list[Any], int]:
    """Override dataclass/dict readings in place-or-replace. Returns (rows, overrides)."""
    if not readings or not uv_map:
        return readings, 0

    from dataclasses import is_dataclass, replace

    out: list[Any] = []
    overrides = 0
    for row in readings:
        if is_dataclass(row) and not isinstance(row, type):
            d = getattr(row, date_attr, None)
            h = getattr(row, hour_attr, None)
            uv = uv_map.get((str(d), int(h))) if d is not None and h is not None else None
            if uv is None:
                out.append(row)
                continue
            out.append(replace(row, **{uv_attr: uv}))
            overrides += 1
            continue

        if isinstance(row, dict):
            d = row.get(date_attr)
            h = row.get(hour_attr)
            uv = uv_map.get((str(d), int(h))) if d is not None and h is not None else None
            if uv is None:
                out.append(row)
                continue
            updated = dict(row)
            updated[uv_attr] = uv
            out.append(updated)
            overrides += 1
            continue

        out.append(row)
    return out, overrides
