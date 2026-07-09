"""Ensure scan preserves Skintruth weather API fields and visuals."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.scan import ScanRequest
from app.hlhp.services.scan_service import run_scan

_SKINTRUTH_PAYLOAD = {
    "data": {
        "weather": {
            "skinCareTip": "Lightweight Day!",
            "current": {
                "temperature": 31,
                "humidity": 72,
                "uv": 8,
                "overallAQI": 145,
                "screenVariants": [
                    {
                        "screen": "mobile",
                        "weatherType": "sunny",
                        "backgroundImage": "https://cdn.example.com/bg-mobile.png",
                        "animal": "https://cdn.example.com/mascot-mobile.png",
                    }
                ],
            },
        },
        "location": {"city": "Mumbai", "state": "Maharashtra", "area": "Bandra"},
    }
}


def _mock_env() -> EnvironmentalData:
    return EnvironmentalData(
        uv_index=8.0,
        temperature_c=31.0,
        aqi=145,
        humidity_pct=72.0,
        location_name="Bandra, Mumbai, Maharashtra",
        fetched_at=datetime.now(timezone.utc),
        data_sources={"weather": "skintruth", "aqi": "skintruth", "uv": "skintruth"},
        raw_weather_payload=_SKINTRUTH_PAYLOAD,
        weather_api_url="https://weather.example/v1/weathers/location-weather",
    )


def test_run_scan_preserves_weather_visuals_and_payload():
    req = ScanRequest(
        user_id=None,
        city="Mumbai",
        local_time=datetime(2026, 6, 18, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        latitude=19.06,
        longitude=72.83,
    )
    with patch(
        "app.hlhp.services.scan_service.fetch_environmental_data",
        new=AsyncMock(return_value=_mock_env()),
    ):
        resp = asyncio.run(run_scan(req))

    assert resp.weather_api_url == "https://weather.example/v1/weathers/location-weather"
    assert resp.raw_weather_payload == _SKINTRUTH_PAYLOAD
    assert resp.skin_care_tip == "Lightweight Day!"
    assert resp.weather_visuals is not None
    assert resp.weather_visuals.weather_type == "sunny"
    assert len(resp.weather_visuals.screen_variants) == 1
    variant = resp.weather_visuals.screen_variants[0]
    assert variant.background_image == "https://cdn.example.com/bg-mobile.png"
    assert variant.animal_image == "https://cdn.example.com/mascot-mobile.png"
    assert resp.env_snapshot.city == "Bandra, Mumbai, Maharashtra"
