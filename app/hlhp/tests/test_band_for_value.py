"""Band lookup must cover every finite reading — never fall through to Extreme Heat."""

from __future__ import annotations

import math

import pytest

from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.scenario_engine import (
    band_for_value,
    dominant_driver,
    driver_states,
    lookup_guest_single_cell,
)


@pytest.fixture(scope="module")
def store():
    return get_scenario_store()


def _keys(store, factor: str) -> list[str]:
    return [str(r.get("key")) for r in store.bands[factor]]


@pytest.mark.parametrize(
    ("temp_c", "expected"),
    [
        (4.9, "extreme_cold"),
        (5.0, "cold"),
        (14.0, "cold"),
        (14.5, "cold"),  # gap → keep prior continuous band
        (15.0, "cool"),
        (19.5, "cool"),
        (20.0, "optimal"),
        (27.0, "optimal"),
        (27.1, "optimal"),  # the live Mumbai heatwave bug
        (27.9, "optimal"),
        (28.0, "warm"),
        (34.5, "warm"),
        (35.0, "hot"),
        (42.0, "hot"),
        (42.1, "extreme_heat"),
        (50.0, "extreme_heat"),
    ],
)
def test_temperature_gaps_never_become_extreme_heat(store, temp_c, expected):
    band = band_for_value(store, "Temperature", temp_c)
    assert band["key"] == expected


@pytest.mark.parametrize(
    ("uvi", "expected"),
    [
        (0.0, "low"),
        (2.0, "low"),
        (2.5, "low"),
        (3.0, "moderate"),
        (5.5, "moderate"),
        (6.0, "high"),
        (7.5, "high"),
        (8.0, "very_high"),
        (10.5, "very_high"),
        (11.0, "extreme"),
        (15.0, "extreme"),
    ],
)
def test_uv_gaps_covered(store, uvi, expected):
    assert band_for_value(store, "UV", uvi)["key"] == expected


@pytest.mark.parametrize(
    ("rh", "expected"),
    [
        (9.9, "critical_low"),
        (10.0, "very_low"),
        (19.5, "very_low"),
        (20.0, "low"),
        (39.5, "low"),
        (40.0, "optimal"),
        (60.5, "optimal"),
        (61.0, "high"),
        (79.5, "high"),
        (80.0, "very_high"),
        (89.5, "very_high"),
        (90.0, "very_high"),
        (90.1, "extreme"),
    ],
)
def test_humidity_gaps_covered(store, rh, expected):
    assert band_for_value(store, "Humidity", rh)["key"] == expected


@pytest.mark.parametrize(
    ("aqi", "expected"),
    [
        (0, "good"),
        (50, "good"),
        (50.5, "good"),
        (51, "satisfactory"),
        (100.5, "satisfactory"),
        (101, "moderate"),
        (200.5, "moderate"),
        (201, "poor"),
        (300.5, "poor"),
        (301, "very_poor"),
        (400, "very_poor"),
        (400.5, "severe"),
        (401, "severe"),
    ],
)
def test_aqi_gaps_covered(store, aqi, expected):
    assert band_for_value(store, "AQI", float(aqi))["key"] == expected


def test_all_factors_cover_dense_samples_without_last_row_fallback(store):
    """No finite sample may land on a band solely because it is rows[-1]."""
    samples = {
        "Temperature": [x / 10 for x in range(-100, 551)],  # -10.0 .. 55.0
        "UV": [x / 10 for x in range(0, 151)],  # 0.0 .. 15.0
        "Humidity": [x / 10 for x in range(0, 1001)],  # 0.0 .. 100.0
        "AQI": [float(x) for x in range(0, 501)],
    }
    for factor, values in samples.items():
        last_key = _keys(store, factor)[-1]
        for val in values:
            key = band_for_value(store, factor, val)["key"]
            assert key in _keys(store, factor)
            # Last-row keys are valid only at the extreme end of each axis.
            if key == last_key:
                if factor == "Temperature":
                    assert val > 42
                elif factor == "UV":
                    assert val >= 11
                elif factor == "Humidity":
                    assert val > 90
                elif factor == "AQI":
                    assert val > 400


def test_mumbai_rainy_27_1_is_not_heatwave_guest_alert(store):
    env = EnvironmentalData(
        temperature_c=27.1,
        uv_index=0.3,
        aqi=52,
        humidity_pct=87.0,
        location_name="Vikhroli West, Mumbai",
    )
    drivers = driver_states(store, env)
    temp = next(d for d in drivers if d.factor == "Temperature")
    assert temp.band_key == "optimal"
    assert dominant_driver(drivers).factor != "Temperature" or dominant_driver(drivers).band_key != "extreme_heat"
    cell = lookup_guest_single_cell(store, drivers, "Normal")
    assert cell is not None
    assert "Heatwave" not in str(cell.get("l0", ""))
    assert cell.get("id") != "G-T-EXTR-NOR-031"


def test_partition_start_for_open_upper_is_exclusive():
    from app.hlhp.services.scenario_engine import _band_partition_start

    start = _band_partition_start(">42°C")
    assert start == math.nextafter(42.0, float("inf"))
    assert 42.0 < start
