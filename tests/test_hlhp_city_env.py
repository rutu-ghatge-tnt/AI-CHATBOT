"""Unit tests for city env slot extraction + scoring (no network)."""

from app.hlhp.services.city_env_collector import (
    average_slot_metrics,
    extract_slot_metrics,
)
from app.hlhp.services.city_env_store import city_key_from_label
from app.hlhp.services.weatherapi_timeline import SFI_SLOT_HOURS


def _hour(date_iso: str, hour: int, *, temp: float, uv: float, rh: float, aqi: float) -> dict:
    return {
        "time": f"{date_iso} {hour:02d}:00",
        "temp_c": temp,
        "uv": uv,
        "humidity": rh,
        "wind_kph": 10,
        "air_quality": {"us-epa-index": 2, "pm2_5": aqi},
    }


def test_city_key_from_label():
    assert city_key_from_label("Pune") == "pune"
    assert city_key_from_label("New Delhi") == "new_delhi"


def test_extract_slot_metrics_all_hours():
    date_iso = "2026-07-22"
    hours = [
        _hour(date_iso, h, temp=30 + h * 0.1, uv=8, rh=60, aqi=40) for h in SFI_SLOT_HOURS
    ]
    payload = {"forecast": {"forecastday": [{"date": date_iso, "hour": hours}]}}
    slots = extract_slot_metrics(payload, date_iso)
    assert len(slots) == len(SFI_SLOT_HOURS)
    assert slots[0]["slot_hour"] == 6
    assert slots[-1]["slot_hour"] == 21
    avg = average_slot_metrics(slots)
    assert avg is not None
    assert avg["slots_count"] == len(SFI_SLOT_HOURS)
    assert 0 <= avg["aqi"] <= 500


def test_extract_slot_metrics_empty_payload():
    assert extract_slot_metrics(None, "2026-07-22") == []
    assert extract_slot_metrics({}, "2026-07-22") == []
    assert average_slot_metrics([]) is None


def test_scheduler_disabled_by_env(monkeypatch):
    from app.hlhp.services import city_env_scheduler as sched

    monkeypatch.setenv("HLHP_CITY_ENV_SCHEDULER", "0")
    monkeypatch.setenv("WEATHERAPI_KEY", "test-key")
    assert sched.scheduler_enabled() is False


def test_scheduler_poll_floor(monkeypatch):
    from app.hlhp.services import city_env_scheduler as sched

    monkeypatch.setenv("HLHP_CITY_ENV_POLL_SECONDS", "10")
    assert sched.poll_seconds() == 300
