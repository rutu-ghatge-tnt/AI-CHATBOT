"""WeatherAPI.com multi-day forecast for HLHP plan-week scoring.

UV is overridden from Open-Meteo daily uv_index_max when available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from app.hlhp.config import hl_settings
from app.hlhp.services import open_meteo_uv
from app.hlhp.services.weather_http import get_json
from app.hlhp.services.weather_quota import PROVIDER_WEATHERAPI
from app.hlhp.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "hl:weatherapi:forecast:v2"


@dataclass(frozen=True)
class ForecastDayReading:
    date: str
    temp_c: float
    humidity_pct: float
    uv_index: float
    aqi: int
    condition_text: str
    is_today: bool


def _to_float(value, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def aqi_from_air_quality(aq: dict | None, *, fallback: int = 50) -> int:
    """Map WeatherAPI air_quality block to a single AQI integer (CPCB-ish scale)."""
    if not aq:
        return fallback
    pm25 = aq.get("pm2_5")
    if pm25 is not None:
        v = float(pm25)
        if v <= 30:
            return max(1, int(round(v * 1.6)))
        if v <= 60:
            return int(round(48 + (v - 30) * 1.4))
        if v <= 90:
            return int(round(90 + (v - 60) * 1.5))
        if v <= 120:
            return int(round(135 + (v - 90) * 1.7))
        return int(round(min(400, 186 + (v - 120) * 2.0)))
    epa = aq.get("us-epa-index")
    if epa is not None:
        return {1: 45, 2: 90, 3: 140, 4: 200, 5: 300, 6: 400}.get(int(epa), fallback)
    return fallback


def _aqi_from_hourly(hours: list[dict], *, fallback: int) -> int:
    if not hours:
        return fallback
    midday = hours[len(hours) // 2]
    return aqi_from_air_quality(midday.get("air_quality"), fallback=fallback)


def _parse_forecast_payload(data: dict, *, days: int) -> list[ForecastDayReading]:
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    forecast = data.get("forecast") if isinstance(data.get("forecast"), dict) else {}
    forecast_days = forecast.get("forecastday") if isinstance(forecast.get("forecastday"), list) else []

    readings: list[ForecastDayReading] = []
    last_aqi = aqi_from_air_quality(current.get("air_quality"))

    for i, fd in enumerate(forecast_days[:days]):
        if not isinstance(fd, dict):
            continue
        date_key = str(fd.get("date") or "")
        day_block = fd.get("day") if isinstance(fd.get("day"), dict) else {}
        hours = fd.get("hour") if isinstance(fd.get("hour"), list) else []
        condition = day_block.get("condition") if isinstance(day_block.get("condition"), dict) else {}

        if i == 0 and current:
            temp_c = _to_float(current.get("temp_c"), 25.0)
            humidity = _to_float(current.get("humidity"), 50.0)
            uvi = round(_to_float(current.get("uv"), 5.0), 1)
            aqi = last_aqi
            cond_text = str((current.get("condition") or {}).get("text") or condition.get("text") or "")
        else:
            temp_c = _to_float(
                day_block.get("avgtemp_c", day_block.get("maxtemp_c")),
                25.0,
            )
            humidity = _to_float(day_block.get("avghumidity"), 50.0)
            uvi = round(_to_float(day_block.get("uv"), 5.0), 1)
            aqi = _aqi_from_hourly(hours, fallback=last_aqi)
            cond_text = str(condition.get("text") or "")

        last_aqi = aqi
        readings.append(
            ForecastDayReading(
                date=date_key,
                temp_c=temp_c,
                humidity_pct=humidity,
                uv_index=uvi,
                aqi=aqi,
                condition_text=cond_text,
                is_today=i == 0,
            )
        )
    return readings


async def fetch_weatherapi_forecast(
    latitude: float,
    longitude: float,
    *,
    days: int = 3,
) -> list[ForecastDayReading]:
    """Fetch up to 3 days from WeatherAPI forecast.json (requires WEATHERAPI_KEY)."""
    key = hl_settings.WEATHERAPI_KEY
    if not key:
        logger.warning("WEATHERAPI_KEY not set — plan-week forecast unavailable")
        return []

    days = max(1, min(int(days), 3))
    cache_key = f"{_CACHE_PREFIX}:{round(latitude, 2)}:{round(longitude, 2)}:{days}"
    cached = await get_cached(cache_key)
    if cached and isinstance(cached.get("readings"), list):
        return [
            ForecastDayReading(**row)
            for row in cached["readings"]
            if isinstance(row, dict)
        ]

    params = {
        "key": key,
        "q": f"{latitude},{longitude}",
        "days": days,
        "aqi": "yes",
    }
    try:
        data = await get_json(
            hl_settings.WEATHERAPI_FORECAST_URL,
            params=params,
            timeout=12,
            provider=PROVIDER_WEATHERAPI,
        )
        if not isinstance(data, dict):
            return []
        readings = _parse_forecast_payload(data, days=days)
        if readings:
            daily_uv = await open_meteo_uv.fetch_daily_uv_max(
                latitude, longitude, days=days
            )
            if daily_uv:
                readings = [
                    replace(row, uv_index=daily_uv[row.date])
                    if row.date in daily_uv
                    else row
                    for row in readings
                ]
            await set_cached(
                cache_key,
                {"readings": [r.__dict__ for r in readings]},
                hl_settings.FORECAST_CACHE_TTL,
            )
        return readings
    except Exception as exc:
        logger.warning(
            "WeatherAPI forecast failed for %s,%s: %s",
            latitude,
            longitude,
            exc,
        )
        return []
