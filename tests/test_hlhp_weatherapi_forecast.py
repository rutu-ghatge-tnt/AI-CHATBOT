"""CPCB NAQI + WeatherAPI forecast parsing tests."""

from app.hlhp.services.cpcb_aqi import (
    aqi_from_weatherapi_air_quality,
    calculate_sub_index,
    cpcb_aqi_from_concentrations,
)
from app.hlhp.services.weatherapi_forecast import (
    ForecastDayReading,
    _parse_forecast_payload,
    aqi_from_air_quality,
)


def test_cpcb_pm25_worked_examples():
    # IES / CPCB examples (sub-index rounded to nearest integer)
    assert round(calculate_sub_index(45, "pm25") or 0) == 75
    assert round(calculate_sub_index(150, "pm25") or 0) == 323
    assert round(calculate_sub_index(20, "pm25") or 0) == 33


def test_cpcb_overall_is_max_sub_index():
    # Skintruth Mumbai-shaped sample: O3 drives overallAQI ≈ 65
    aqi = cpcb_aqi_from_concentrations(
        pm25=19.6,
        pm10=50.5,
        co_mg=163 / 1000,
        no2=7.1,
        o3=65,
        so2=5.9,
    )
    assert aqi == 65


def test_aqi_from_weatherapi_uses_all_pollutants():
    aqi = aqi_from_weatherapi_air_quality(
        {
            "pm2_5": 19.6,
            "pm10": 50.5,
            "co": 163,
            "no2": 7.1,
            "o3": 65,
            "so2": 5.9,
        }
    )
    assert aqi == 65


def test_aqi_from_pm25_bands():
    assert aqi_from_air_quality({"pm2_5": 20}) < 50
    assert aqi_from_air_quality({"pm2_5": 80}) > 100
    # Low PM alone must not collapse to single-digit fake AQI
    assert aqi_from_air_quality({"pm2_5": 5.6}) >= 9


def test_aqi_fallback_epa_and_empty():
    assert aqi_from_air_quality({"us-epa-index": 2}) == 90
    assert aqi_from_air_quality(None) == 50
    assert aqi_from_air_quality({}) == 50


def test_parse_forecast_payload_three_days():
    payload = {
        "current": {
            "temp_c": 28.0,
            "humidity": 65,
            "uv": 6.0,
            "condition": {"text": "Partly cloudy"},
            "air_quality": {"pm2_5": 35.0, "us-epa-index": 2},
        },
        "forecast": {
            "forecastday": [
                {
                    "date": "2026-06-18",
                    "day": {
                        "avgtemp_c": 29.0,
                        "avghumidity": 70,
                        "uv": 7.0,
                        "condition": {"text": "Sunny"},
                    },
                    "hour": [],
                },
                {
                    "date": "2026-06-19",
                    "day": {
                        "avgtemp_c": 30.0,
                        "avghumidity": 72,
                        "uv": 8.0,
                        "condition": {"text": "Hot"},
                    },
                    "hour": [{"air_quality": {"pm2_5": 40.0}}],
                },
                {
                    "date": "2026-06-20",
                    "day": {
                        "avgtemp_c": 27.0,
                        "avghumidity": 80,
                        "uv": 4.0,
                        "condition": {"text": "Rain"},
                    },
                    "hour": [],
                },
            ]
        },
    }
    readings = _parse_forecast_payload(payload, days=3)
    assert len(readings) == 3
    assert readings[0].is_today is True
    assert readings[0].temp_c == 28.0
    assert readings[1].date == "2026-06-19"
    assert isinstance(readings[1], ForecastDayReading)
    # PM2.5=35 → CPCB satisfactory band (~58)
    assert 51 <= readings[0].aqi <= 100
