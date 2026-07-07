"""Tests for daily recap driver selection."""

from app.hlhp.core.sfi_driver import COMFORT_SFI_THRESHOLD, driver_key_for_day
from app.hlhp.models.environmental import EnvironmentalData


def _env(**kwargs) -> EnvironmentalData:
    defaults = dict(
        uv_index=6.0,
        temperature_c=28.0,
        aqi=80,
        humidity_pct=55.0,
        location_name="Pune",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def test_comfort_when_daily_average_at_threshold():
    driver = driver_key_for_day(
        outdoor_score_avg=float(COMFORT_SFI_THRESHOLD),
        env=_env(humidity_pct=92.0),
    )
    assert driver == "comfort"


def test_humidity_driver_when_average_below_threshold():
    driver = driver_key_for_day(
        outdoor_score_avg=64.0,
        env=_env(humidity_pct=88.0, uv_index=4.0, temperature_c=27.0, aqi=60),
    )
    assert driver == "humidity"


def test_no_driver_without_daily_average():
    assert driver_key_for_day(outdoor_score_avg=None, env=_env()) is None
