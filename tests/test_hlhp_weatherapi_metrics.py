"""WeatherAPI metrics + Skintruth visuals split."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.weather_fetcher import (
    fetch_environmental_data,
    parse_weatherapi_current,
)


_WA_PAYLOAD = {
    "location": {"name": "Bandra", "region": "Maharashtra"},
    "current": {
        "temp_c": 31.2,
        "humidity": 71,
        "uv": 8.0,
        "wind_kph": 18.5,
        "wind_dir": "SW",
        "gust_kph": 24.0,
        "precip_mm": 0,
        "is_day": 1,
        "condition": {"text": "Partly cloudy"},
        "air_quality": {"pm2_5": 55.0, "us-epa-index": 2},
    },
}

_SKINTRUTH_PAYLOAD = {
    "data": {
        "weather": {
            "skinCareTip": "Lightweight Day!",
            "current": {
                "temperature": 99,
                "humidity": 99,
                "uv": 99,
                "overallAQI": 999,
                "screenVariants": [
                    {
                        "screen": "mobile",
                        "weatherType": "sunny",
                        "backgroundImage": "https://cdn.example.com/bg.png",
                        "animal": "https://cdn.example.com/animal.png",
                    }
                ],
            },
        },
        "location": {"city": "Mumbai", "state": "Maharashtra", "area": "Bandra"},
    }
}


def test_parse_weatherapi_current_metrics():
    m = parse_weatherapi_current(_WA_PAYLOAD)
    assert m["temperature_c"] == 31.2
    assert m["humidity_pct"] == 71.0
    assert m["uv_index"] == 8.0
    assert m["wind_kmh"] == 18.5
    assert m["wind_dir"] == "SW"
    assert m["aqi"] > 0
    assert "Bandra" in m["location_name"]


def test_fetch_environmental_uses_weatherapi_metrics_skintruth_visuals():
    with (
        patch(
            "app.hlhp.services.weather_fetcher.fetch_weatherapi_current",
            new=AsyncMock(return_value=_WA_PAYLOAD),
        ),
        patch(
            "app.hlhp.services.weather_fetcher._fetch_skintruth_visuals",
            new=AsyncMock(
                return_value={
                    "location_name": "Bandra, Mumbai, Maharashtra",
                    "raw_weather_payload": _SKINTRUTH_PAYLOAD,
                }
            ),
        ),
        patch("app.hlhp.services.weather_fetcher.get_cached", new=AsyncMock(return_value=None)),
        patch("app.hlhp.services.weather_fetcher.set_cached", new=AsyncMock()),
    ):
        env = asyncio.run(fetch_environmental_data(19.06, 72.83))

    assert isinstance(env, EnvironmentalData)
    assert env.temperature_c == 31.2
    assert env.humidity_pct == 71.0
    assert env.uv_index == 8.0
    assert env.aqi != 999  # not Skintruth metrics
    assert env.location_name == "Bandra, Mumbai, Maharashtra"
    assert env.raw_weather_payload == _SKINTRUTH_PAYLOAD
    assert env.data_sources.get("weather") == "weatherapi"
    assert env.data_sources.get("visuals") == "skintruth"
    assert isinstance(env.fetched_at, datetime)
