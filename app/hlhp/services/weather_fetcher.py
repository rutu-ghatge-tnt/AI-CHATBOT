from datetime import datetime, timezone

import httpx
import logging

from app.hlhp.config import hl_settings
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.weather_wind import extract_wind_fields
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


async def _fetch_weatherapi_current(lat: float, lng: float) -> dict | None:
    """Direct WeatherAPI current.json — used when Skintruth omits wind fields."""
    key = hl_settings.WEATHERAPI_KEY
    if not key:
        return None
    params = {"key": key, "q": f"{lat},{lng}", "aqi": "yes"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(hl_settings.WEATHERAPI_CURRENT_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("WeatherAPI current fallback failed for %s,%s: %s", lat, lng, exc)
        return None


async def _fetch_skintruth_weather(lat: float, lng: float) -> dict:
    params = {"latitude": lat, "longitude": lng}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(hl_settings.WEATHER_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if not isinstance(data, dict):
        raise ValueError("Skintruth weather payload is not a JSON object")

    payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    weather = payload.get("weather", {}) if isinstance(payload.get("weather"), dict) else {}
    current = weather.get("current", {}) if isinstance(weather.get("current"), dict) else {}
    location = payload.get("location", {}) if isinstance(payload.get("location"), dict) else {}
    weather_location = weather.get("location", {}) if isinstance(weather.get("location"), dict) else {}

    city = _pick_first(location, ["city"], "") or _pick_first(weather_location, ["name"], "")
    state = _pick_first(location, ["state"], "") or _pick_first(weather_location, ["region"], "")
    area = _pick_first(location, ["area"], "") or _pick_first(weather_location, ["area"], "")
    location_name = ", ".join([part for part in [area, city, state] if part]) or "Unknown"

    temp_c = _to_float(_pick_first(current, ["temperature", "temp_c", "tempC"]), 25.0)
    humidity_pct = _to_float(_pick_first(current, ["humidity"]), 50.0)
    uv_index = round(_to_float(_pick_first(current, ["uv", "uv_index", "uvIndex"]), 5.0), 1)
    aqi = _to_int(_pick_first(current, ["overallAQI", "aqi"]), 50)

    wind = extract_wind_fields(data)
    wind_kmh = wind["wind_kmh"]
    wind_dir = wind["wind_dir"]
    gust_kmh = wind["gust_kmh"]

    if wind_kmh <= 0:
        wa = await _fetch_weatherapi_current(lat, lng)
        if wa:
            wa_wind = extract_wind_fields(wa)
            if wa_wind["wind_kmh"] > 0:
                wind_kmh = wa_wind["wind_kmh"]
                wind_dir = wa_wind["wind_dir"] or wind_dir
                gust_kmh = wa_wind["gust_kmh"] or gust_kmh
            if isinstance(wa.get("current"), dict):
                aq = wa["current"].get("air_quality")
                if isinstance(aq, dict) and aqi == 50:
                    from app.hlhp.services.weatherapi_forecast import aqi_from_air_quality

                    aqi = aqi_from_air_quality(aq, fallback=aqi)

    return {
        "temperature_c": temp_c,
        "humidity_pct": humidity_pct,
        "aqi": aqi,
        "uv_index": uv_index,
        "wind_kmh": wind_kmh,
        "wind_dir": wind_dir,
        "gust_kmh": gust_kmh,
        "location_name": location_name,
        "raw_weather_payload": data,
        "weather_api_url": hl_settings.WEATHER_API_URL,
    }


async def fetch_environmental_data(lat: float, lng: float) -> EnvironmentalData:
    cache_key = f"{CACHE_KEY_PREFIX}:{round(lat, 2)}:{round(lng, 2)}"
    cached = await get_cached(cache_key)
    if cached:
        return EnvironmentalData(**cached)

    try:
        source_data = await _fetch_skintruth_weather(lat, lng)
    except Exception as exc:
        logger.warning(
            "HLHP weather API failed for lat=%s lng=%s (%s): %s",
            lat,
            lng,
            hl_settings.WEATHER_API_URL,
            exc,
        )
        source_data = {
            "temperature_c": 25.0,
            "humidity_pct": 50.0,
            "aqi": 50,
            "uv_index": 5.0,
            "wind_kmh": 0.0,
            "wind_dir": "",
            "gust_kmh": 0.0,
            "location_name": "Unknown",
            "raw_weather_payload": {},
            "weather_api_url": hl_settings.WEATHER_API_URL,
        }

    from_api = source_data["location_name"] not in ("Unknown", "")

    env_data = EnvironmentalData(
        uv_index=source_data["uv_index"],
        temperature_c=source_data["temperature_c"],
        aqi=source_data["aqi"],
        humidity_pct=source_data["humidity_pct"],
        wind_kmh=source_data.get("wind_kmh", 0.0),
        wind_dir=source_data.get("wind_dir", ""),
        gust_kmh=source_data.get("gust_kmh", 0.0),
        location_name=source_data["location_name"],
        fetched_at=datetime.now(timezone.utc),
        data_sources={
            "weather": "skintruth" if from_api else "default",
            "aqi": "skintruth" if from_api else "default",
            "uv": "skintruth" if from_api else "default",
        },
        raw_weather_payload=source_data["raw_weather_payload"],
        weather_api_url=source_data["weather_api_url"],
    )

    if from_api:
        await set_cached(cache_key, env_data.model_dump(mode="json"), hl_settings.WEATHER_CACHE_TTL)
    return env_data

