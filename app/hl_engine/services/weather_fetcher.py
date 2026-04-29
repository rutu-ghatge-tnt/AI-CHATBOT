from datetime import datetime, timezone

import httpx

from app.hl_engine.config import hl_settings
from app.hl_engine.models.environmental import EnvironmentalData
from app.hl_engine.utils.cache import get_cached, set_cached

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

    temp_c = _to_float(_pick_first(current, ["temperature"]), 25.0)
    humidity_pct = _to_float(_pick_first(current, ["humidity"]), 50.0)
    uv_index = round(_to_float(_pick_first(current, ["uv"]), 5.0), 1)
    aqi = _to_int(_pick_first(current, ["overallAQI", "aqi"]), 50)

    return {
        "temperature_c": temp_c,
        "humidity_pct": humidity_pct,
        "aqi": aqi,
        "uv_index": uv_index,
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
    except Exception:
        source_data = {
            "temperature_c": 25.0,
            "humidity_pct": 50.0,
            "aqi": 50,
            "uv_index": 5.0,
            "location_name": "Unknown",
            "raw_weather_payload": {},
            "weather_api_url": hl_settings.WEATHER_API_URL,
        }

    env_data = EnvironmentalData(
        uv_index=source_data["uv_index"],
        temperature_c=source_data["temperature_c"],
        aqi=source_data["aqi"],
        humidity_pct=source_data["humidity_pct"],
        location_name=source_data["location_name"],
        fetched_at=datetime.now(timezone.utc),
        data_sources={
            "weather": "skintruth" if source_data["location_name"] != "Unknown" else "default",
            "aqi": "skintruth" if source_data["location_name"] != "Unknown" else "default",
            "uv": "skintruth" if source_data["location_name"] != "Unknown" else "default",
        },
        raw_weather_payload=source_data["raw_weather_payload"],
        weather_api_url=source_data["weather_api_url"],
    )

    await set_cached(cache_key, env_data.model_dump(mode="json"), hl_settings.WEATHER_CACHE_TTL)
    return env_data

