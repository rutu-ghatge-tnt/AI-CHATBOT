"""Map HLHP runtime bands (core/bands.py) to patterns engine + scenario library keys."""

from __future__ import annotations

import re

# bands.py vocabulary -> adverse for exposure counting (engine drivers)
ADVERSE_BANDS: dict[str, set[str]] = {
    "temp": {"warm", "hot", "very_hot"},
    "uv": {"high", "very_high", "extreme"},
    "humidity": {"high", "very_high"},
    "aqi": {"poor", "very_poor", "severe"},
}

# Engine driver -> scenario workbook factor slug
ENGINE_DRIVER_TO_FACTOR: dict[str, str] = {
    "temp": "temperature",
    "uv": "uv",
    "humidity": "humidity",
    "aqi": "aqi",
}

# bands.py band_key -> scenario library band key (per driver)
_BAND_TO_SCENARIO: dict[str, dict[str, str]] = {
    "temp": {
        "very_cold": "extreme_cold",
        "cold": "cold",
        "comfortable": "optimal",
        "warm": "warm",
        "hot": "hot",
        "very_hot": "extreme_heat",
    },
    "uv": {
        "off": "low",
        "low": "low",
        "moderate": "moderate",
        "high": "high",
        "very_high": "very_high",
        "extreme": "extreme",
    },
    "humidity": {
        "very_low": "very_low",
        "low": "low",
        "comfortable": "optimal",
        "high": "high",
        "very_high": "very_high",
    },
    "aqi": {
        "good": "good",
        "satisfactory": "satisfactory",
        "moderate": "moderate",
        "poor": "poor",
        "very_poor": "very_poor",
        "severe": "severe",
    },
}

# Intensity proxy for correlation chart bars (0–1)
BAND_INTENSITY: dict[str, float] = {
    "off": 0.25,
    "very_cold": 0.30,
    "extreme_cold": 0.30,
    "cold": 0.35,
    "cool": 0.40,
    "low": 0.30,
    "very_low": 0.28,
    "good": 0.30,
    "satisfactory": 0.40,
    "comfortable": 0.40,
    "optimal": 0.40,
    "moderate": 0.55,
    "warm": 0.65,
    "high": 0.80,
    "hot": 0.88,
    "poor": 0.75,
    "very_high": 0.92,
    "very_hot": 0.95,
    "extreme_heat": 1.0,
    "extreme": 1.0,
    "severe": 0.95,
    "very_poor": 0.85,
}


def slug(value: str) -> str:
    return re.sub(r"^_|_$", "", re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()))


def map_band_to_scenario(driver: str, band_key: str | None) -> str:
    if not band_key:
        return "optimal"
    return _BAND_TO_SCENARIO.get(driver, {}).get(band_key, band_key)


def scenario_master_key(driver: str, band_key: str | None, skin: str, concern: str) -> str:
    factor = ENGINE_DRIVER_TO_FACTOR.get(driver, driver)
    mapped = map_band_to_scenario(driver, band_key)
    return f"{factor}|{mapped}|{slug(skin)}|{slug(concern)}"


def band_intensity(band_key: str | None) -> float:
    if not band_key:
        return 0.35
    return BAND_INTENSITY.get(band_key, 0.35)


def daily_doc_band_keys(doc: dict) -> dict[str, str]:
    """Build engine EnvDay.band_keys from hlhp_daily_log document."""
    return {
        "temp": str(doc.get("temp_band") or ""),
        "uv": str(doc.get("uv_band") or ""),
        "humidity": str(doc.get("humidity_band") or ""),
        "aqi": str(doc.get("aqi_band") or ""),
    }
