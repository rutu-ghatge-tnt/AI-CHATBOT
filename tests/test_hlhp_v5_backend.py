"""Tests for weather wind extraction and surge detection."""

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.surge_detector import assess_surge
from app.hlhp.services.weather_wind import extract_wind_fields
from app.hlhp.services.v4_scoring_engine import personal_sfi, band_map, scene_key


def test_extract_wind_from_weatherapi_current():
    payload = {
        "current": {
            "temp_c": 28,
            "wind_kph": 32.5,
            "wind_dir": "SSW",
            "gust_kph": 41.2,
        }
    }
    wind = extract_wind_fields(payload)
    assert wind["wind_kmh"] == 32.5
    assert wind["wind_dir"] == "SSW"
    assert wind["gust_kmh"] == 41.2


def test_extract_wind_from_mph():
    payload = {"current": {"wind_mph": 20}}
    wind = extract_wind_fields(payload)
    assert 31.0 <= wind["wind_kmh"] <= 33.0


def test_surge_from_rolling_delta():
    env = EnvironmentalData(
        uv_index=6,
        temperature_c=34,
        aqi=80,
        humidity_pct=78,
        wind_kmh=10,
        location_name="Pune",
    )
    baseline = {"uvi_avg": 4.0, "temp_avg": 28.0, "aqi_avg": 70, "rh_avg": 55.0}
    result = assess_surge(env, baseline=baseline)
    assert result.active
    assert "heat_surge" in result.tags
    assert "humidity_surge" in result.tags


def test_surge_absolute_aqi():
    env = EnvironmentalData(
        uv_index=5,
        temperature_c=28,
        aqi=220,
        humidity_pct=50,
        wind_kmh=8,
        location_name="Delhi",
    )
    result = assess_surge(env)
    assert result.active
    assert "pollution_surge" in result.tags


def test_surge_force_demo():
    env = EnvironmentalData(
        uv_index=5,
        temperature_c=28,
        aqi=50,
        humidity_pct=50,
        wind_kmh=8,
        location_name="Pune",
    )
    result = assess_surge(env, force=True)
    assert result.active
    assert result.forced


def test_scene_windy_with_wind_kph():
    env = EnvironmentalData(
        uv_index=5,
        temperature_c=28,
        aqi=50,
        humidity_pct=50,
        wind_kmh=35,
        location_name="Ahmedabad",
    )
    assert scene_key(env) == "windy"


def test_skin_band_penalty_dry_very_low_humidity():
    env = EnvironmentalData(
        uv_index=2,
        temperature_c=22,
        aqi=40,
        humidity_pct=15,
        wind_kmh=5,
        location_name="Jaipur",
    )
    bands = band_map(env)
    score = personal_sfi(bands, "Eczema", "Dry")
    # Weighted base minus dry/very_low humidity penalty (10)
    assert score < 100
