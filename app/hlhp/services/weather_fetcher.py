"""HLHP environmental fetch.

Metrics (temp / humidity / UV / AQI / wind) come from WeatherAPI (`WEATHERAPI_KEY`).
Skintruth location-weather is used only for place labels + background/animal imagery.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.hlhp.config import hl_settings
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.weather_wind import extract_wind_fields
from app.hlhp.services.weatherapi_forecast import aqi_from_air_quality
from app.hlhp.utils.cache import get_cached, set_cached

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "hl:weather"


def _pick_first(data: dict, keys: list[str], default=None):
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def _to_int(value, default: int) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_weatherapi_current(data: dict) -> dict:
    """Normalize WeatherAPI current.json (or forecast current block) into metrics."""
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    location = data.get("location") if isinstance(data.get("location"), dict) else {}

    wind = extract_wind_fields(data)
    aq = current.get("air_quality") if isinstance(current.get("air_quality"), dict) else None

    city = str(location.get("name") or "").strip()
    region = str(location.get("region") or "").strip()
    location_name = ", ".join([p for p in [city, region] if p]) or "Unknown"

    return {
        "temperature_c": _to_float(current.get("temp_c"), 25.0),
        "humidity_pct": _to_float(current.get("humidity"), 50.0),
        "uv_index": round(_to_float(current.get("uv"), 5.0), 1),
        "aqi": aqi_from_air_quality(aq, fallback=50),
        "wind_kmh": wind["wind_kmh"],
        "wind_dir": wind["wind_dir"],
        "gust_kmh": wind["gust_kmh"],
        "location_name": location_name,
        "condition_text": str((current.get("condition") or {}).get("text") or ""),
        "precip_mm": _to_float(current.get("precip_mm"), 0.0),
        "is_day": bool(current.get("is_day", 1)),
    }


async def fetch_weatherapi_current(lat: float, lng: float) -> dict | None:
    """Direct WeatherAPI current.json with AQI."""
    key = hl_settings.WEATHERAPI_KEY
    if not key:
        logger.warning("WEATHERAPI_KEY not set — cannot fetch live weather metrics")
        return None
    params = {"key": key, "q": f"{lat},{lng}", "aqi": "yes"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(hl_settings.WEATHERAPI_CURRENT_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("WeatherAPI current failed for %s,%s: %s", lat, lng, exc)
        return None


async def fetch_weatherapi_current_by_query(query: str) -> dict | None:
    """WeatherAPI current by city name / lat,lng string."""
    key = hl_settings.WEATHERAPI_KEY
    if not key:
        return None
    params = {"key": key, "q": query, "aqi": "yes"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(hl_settings.WEATHERAPI_CURRENT_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("WeatherAPI current failed for q=%s: %s", query, exc)
        return None


async def _fetch_skintruth_visuals(lat: float, lng: float) -> dict:
    """Skintruth location-weather — location label + imagery payload only."""
    params = {"latitude": lat, "longitude": lng}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(hl_settings.WEATHER_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict):
        raise ValueError("Skintruth weather payload is not a JSON object")

    payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    weather = payload.get("weather", {}) if isinstance(payload.get("weather"), dict) else {}
    location = payload.get("location", {}) if isinstance(payload.get("location"), dict) else {}
    weather_location = weather.get("location", {}) if isinstance(weather.get("location"), dict) else {}

    city = _pick_first(location, ["city"], "") or _pick_first(weather_location, ["name"], "")
    state = _pick_first(location, ["state"], "") or _pick_first(weather_location, ["region"], "")
    area = _pick_first(location, ["area"], "") or _pick_first(weather_location, ["area"], "")
    location_name = ", ".join([part for part in [area, city, state] if part]) or ""

    return {
        "location_name": location_name,
        "raw_weather_payload": data,
    }


# Back-compat alias used by older call sites / tests
async def _fetch_weatherapi_current(lat: float, lng: float) -> dict | None:
    return await fetch_weatherapi_current(lat, lng)


async def fetch_environmental_data(lat: float, lng: float) -> EnvironmentalData:
    cache_key = f"{CACHE_KEY_PREFIX}:{round(lat, 2)}:{round(lng, 2)}"
    cached = await get_cached(cache_key)
    if cached:
        return EnvironmentalData(**cached)

    wa_task = asyncio.create_task(fetch_weatherapi_current(lat, lng))
    st_task = asyncio.create_task(_fetch_skintruth_visuals(lat, lng))

    wa_raw, st_meta = await asyncio.gather(wa_task, st_task, return_exceptions=True)

    metrics: dict | None = None
    if isinstance(wa_raw, dict):
        metrics = parse_weatherapi_current(wa_raw)
    elif isinstance(wa_raw, Exception):
        logger.warning("WeatherAPI metrics failed for %s,%s: %s", lat, lng, wa_raw)

    skintruth_location = ""
    raw_payload: dict = {}
    if isinstance(st_meta, dict):
        skintruth_location = str(st_meta.get("location_name") or "")
        raw_payload = st_meta.get("raw_weather_payload") or {}
    elif isinstance(st_meta, Exception):
        logger.warning(
            "Skintruth visuals failed for lat=%s lng=%s (%s): %s",
            lat,
            lng,
            hl_settings.WEATHER_API_URL,
            st_meta,
        )

    if metrics is None:
        metrics = {
            "temperature_c": 25.0,
            "humidity_pct": 50.0,
            "aqi": 50,
            "uv_index": 5.0,
            "wind_kmh": 0.0,
            "wind_dir": "",
            "gust_kmh": 0.0,
            "location_name": "Unknown",
            "condition_text": "",
            "precip_mm": 0.0,
            "is_day": True,
        }
        metrics_source = "default"
    else:
        metrics_source = "weatherapi"

    location_name = skintruth_location or metrics.get("location_name") or "Unknown"
    from_live = metrics_source == "weatherapi"

    env_data = EnvironmentalData(
        uv_index=metrics["uv_index"],
        temperature_c=metrics["temperature_c"],
        aqi=metrics["aqi"],
        humidity_pct=metrics["humidity_pct"],
        wind_kmh=metrics.get("wind_kmh", 0.0),
        wind_dir=metrics.get("wind_dir", ""),
        gust_kmh=metrics.get("gust_kmh", 0.0),
        location_name=location_name,
        fetched_at=datetime.now(timezone.utc),
        data_sources={
            "weather": metrics_source,
            "aqi": metrics_source,
            "uv": metrics_source,
            "location": "skintruth" if skintruth_location else metrics_source,
            "visuals": "skintruth" if raw_payload else "none",
        },
        raw_weather_payload=raw_payload if isinstance(raw_payload, dict) else {},
        weather_api_url=hl_settings.WEATHERAPI_CURRENT_URL
        if metrics_source == "weatherapi"
        else hl_settings.WEATHER_API_URL,
    )

    if from_live:
        await set_cached(cache_key, env_data.model_dump(mode="json"), hl_settings.WEATHER_CACHE_TTL)
    return env_data
