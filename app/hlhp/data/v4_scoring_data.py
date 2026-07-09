"""
HLHP V4 scoring tables — port from HLHP V4 Backend Handoff (July 2026).

SKIN_BAND_PENALTY matches the V5 interactive prototype (hlhp-interactive / export-prep).
Override at runtime via ``data/skin_band_penalty.json`` (see scripts/update_hlhp_library.py).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

_DATA_DIR = Path(__file__).resolve().parent
_PENALTY_JSON = _DATA_DIR / "skin_band_penalty.json"


class BandRow(TypedDict):
    key: str
    label: str
    points: int


FACTOR_ORDER = ("Temperature", "UV", "Humidity", "AQI")

DEFAULT_WEIGHTS: dict[str, float] = {f: 1.0 for f in FACTOR_ORDER}

CONCERN_WEIGHTS: dict[str, dict[str, float]] = {
    "Melasma": {"Temperature": 1, "AQI": 1, "UV": 2, "Humidity": 0.5},
    "Uneven Tone": {"Temperature": 1, "AQI": 1, "UV": 2, "Humidity": 0.5},
    "Acne": {"Temperature": 0.5, "AQI": 1.5, "UV": 0.5, "Humidity": 1.5},
    "Eczema": {"Temperature": 1, "AQI": 1, "UV": 0.5, "Humidity": 2},
}

CONCERN_V4_MAP: dict[str, str] = {
    "melasma": "Melasma",
    "dullness": "Uneven Tone",
    "tan": "Uneven Tone",
    "pigmentation": "Uneven Tone",
    "acne": "Acne",
    "redness": "Eczema",
    "sensitivity": "Eczema",
}

SKIN_V4_KEYS = frozenset({"dry", "oily", "combination", "normal", "sensitive"})

# Full Band × Skin penalty matrix (V5 prototype / hlhp-interactive.html)
_BUILTIN_SKIN_BAND_PENALTY: dict[str, dict[str, dict[str, int]]] = {
    "Humidity": {
        "very_low": {"normal": 3, "dry": 10, "oily": 0, "sensitive": 5, "combination": 5},
        "low": {"normal": 1, "dry": 6, "oily": 0, "sensitive": 2, "combination": 3},
        "optimal": {},
        "high": {"normal": 1, "dry": 0, "oily": 6, "sensitive": 2, "combination": 3},
        "very_high": {"normal": 3, "dry": 1, "oily": 10, "sensitive": 4, "combination": 6},
        "extreme": {"normal": 4, "dry": 2, "oily": 12, "sensitive": 6, "combination": 7},
    },
    "UV": {
        "low": {},
        "moderate": {"sensitive": 2},
        "high": {"normal": 1, "dry": 1, "oily": 1, "sensitive": 5, "combination": 1},
        "very_high": {"normal": 2, "dry": 2, "oily": 2, "sensitive": 8, "combination": 3},
        "extreme": {"normal": 3, "dry": 3, "oily": 3, "sensitive": 10, "combination": 4},
    },
    "AQI": {
        "good": {},
        "satisfactory": {"oily": 1, "sensitive": 1},
        "moderate": {"normal": 1, "dry": 2, "oily": 3, "sensitive": 4, "combination": 2},
        "poor": {"normal": 2, "dry": 3, "oily": 5, "sensitive": 6, "combination": 4},
        "very_poor": {"normal": 3, "dry": 4, "oily": 6, "sensitive": 7, "combination": 5},
        "severe": {"normal": 4, "dry": 5, "oily": 7, "sensitive": 8, "combination": 6},
    },
    "Temperature": {
        "cold": {"normal": 2, "dry": 5, "sensitive": 4, "combination": 3},
        "cool": {"dry": 1, "sensitive": 1},
        "optimal": {},
        "warm": {"oily": 2, "sensitive": 2, "combination": 1},
        "hot": {"normal": 2, "dry": 3, "oily": 4, "sensitive": 7, "combination": 3},
        "extreme": {"normal": 3, "dry": 4, "oily": 5, "sensitive": 9, "combination": 4},
        "extreme_heat": {"normal": 3, "dry": 4, "oily": 5, "sensitive": 9, "combination": 4},
    },
}


@lru_cache(maxsize=1)
def load_skin_band_penalty() -> dict[str, dict[str, dict[str, int]]]:
    """Load penalty matrix from JSON override or built-in table."""
    if _PENALTY_JSON.exists():
        try:
            raw = json.loads(_PENALTY_JSON.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw:
                return raw
        except (json.JSONDecodeError, OSError):
            pass
    return _BUILTIN_SKIN_BAND_PENALTY


def reload_skin_band_penalty() -> dict[str, dict[str, dict[str, int]]]:
    load_skin_band_penalty.cache_clear()
    return load_skin_band_penalty()


# Module-level alias used by v4_scoring_engine (reload via reload_skin_band_penalty)
SKIN_BAND_PENALTY = load_skin_band_penalty()

MODE_THRESHOLDS: list[tuple[int, str]] = [
    (85, "Paradise Mode"),
    (70, "Smooth Sailing"),
    (55, "Guard Up"),
    (40, "Battle Stations"),
    (25, "Hostile Mode"),
    (0, "Code Red"),
]
