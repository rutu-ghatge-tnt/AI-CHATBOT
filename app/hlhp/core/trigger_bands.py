"""Trigger band definitions per HLHP Engine Implementation Spec v2 §3."""

from __future__ import annotations

TRIGGER_BANDS: dict[str, dict[str, tuple[float, float] | list[tuple[int, int, str]]]] = {
    "uvi": {
        "off": (0, 0),
        "low": (1, 2),
        "moderate": (3, 5),
        "high": (6, 7),
        "very_high": (8, 10),
        "extreme": (11, 999),
    },
    "aqi": {
        "good": (0, 50),
        "satisfactory": (51, 100),
        "moderate": (101, 200),
        "poor": (201, 300),
        "very_poor": (301, 400),
        "severe": (401, 9999),
    },
    "rh": {
        "very_low": (0, 24.99),
        "low": (25, 39.99),
        "comfortable": (40, 60),
        "high": (60.01, 75),
        "very_high": (75.01, 100),
    },
    "temp": {
        "very_cold": (-999, 9.99),
        "cold": (10, 17.99),
        "comfortable": (18, 27.99),
        "warm": (28, 31.99),
        "hot": (32, 37.99),
        "very_hot": (38, 999),
    },
}

# v1 workbook rows may still author "moderate" for mid RH — treat as comfortable.
_RH_ALIASES = {"moderate": "comfortable"}

# v1 season tags map onto v2 four-band calendar for matching.
_SEASON_ALIASES: dict[str, set[str]] = {
    "winter": {"winter", "winter_dry", "winter_humid"},
    "summer": {"summer", "pre_monsoon"},
    "monsoon": {"monsoon"},
    "post_monsoon": {"post_monsoon"},
    "winter_dry": {"winter_dry", "winter"},
    "winter_humid": {"winter_humid", "winter"},
    "pre_monsoon": {"pre_monsoon", "summer"},
}


def normalize_rh_band(band: str) -> str:
    band = band.strip().lower()
    return _RH_ALIASES.get(band, band)


def season_match_tags(season: str) -> set[str]:
    season = season.strip().lower()
    return _SEASON_ALIASES.get(season, {season})


def trigger_bands_snapshot() -> dict[str, object]:
    """JSON-serialisable band definitions for snapshot embed."""
    return {
        "uvi": {k: list(v) for k, v in TRIGGER_BANDS["uvi"].items()},
        "aqi": {k: list(v) for k, v in TRIGGER_BANDS["aqi"].items()},
        "rh": {k: list(v) for k, v in TRIGGER_BANDS["rh"].items()},
        "temp": {k: list(v) for k, v in TRIGGER_BANDS["temp"].items()},
        "season": ["winter", "summer", "monsoon", "post_monsoon"],
        "rh_aliases": dict(_RH_ALIASES),
        "season_aliases": {k: sorted(v) for k, v in _SEASON_ALIASES.items()},
    }
