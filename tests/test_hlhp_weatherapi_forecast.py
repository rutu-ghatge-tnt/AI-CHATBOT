"""WeatherAPI forecast parsing tests."""

from app.hlhp.services.weatherapi_forecast import (
    ForecastDayReading,
    _parse_forecast_payload,
    aqi_from_air_quality,
)


def test_aqi_from_pm25():
    assert aqi_from_air_quality({"pm2_5": 20}) < 50
    assert aqi_from_air_quality({"pm2_5": 80}) > 100


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
