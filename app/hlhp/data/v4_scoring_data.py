"""
HLHP SFI scoring tables.

Layer separation
----------------
The SFI number is built from exactly three things::

    band points  ->  concern penalty  ->  skin-type penalty

Life stage (age, gender, pregnancy, PCOS, menopause) and the daily feeling log
are NOT in that stack. Scenario Library sheets 12 and 13 specify age/gender
``risk_delta`` as a delta to *base cell risk* with an addendum appended to L2
copy; the feeling log is an outcome signal, not an environmental one. Both act
on copy and alert register via ``sfi_unified``.

All tables are external configuration. Recalibration is a data change, not a
code change. ``conformance_test.py`` asserts they stay in step with the
Scenario Library snapshot.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

_DATA_DIR = Path(__file__).resolve().parent
_SKIN_PENALTY_JSON = _DATA_DIR / "skin_band_penalty.json"
_CONCERN_PENALTY_JSON = _DATA_DIR / "concern_penalty.json"


class BandRow(TypedDict):
    key: str
    label: str
    points: int


FACTOR_ORDER = ("Temperature", "UV", "Humidity", "AQI")


# --------------------------------------------------------------------------
# Environmental weights
# --------------------------------------------------------------------------
# UV first (least reversible, cumulative photodamage); the remaining three held
# equal, which is a more honest claim than an ordering the evidence does not
# support. Ranking pollution level with the barrier factors rather than last
# answers the "AQI ranked last is debatable for India" objection.
#
# Expert priors, NOT fitted. To be finalised by the Delphi/AHP panel.
#
# These need not sum to 1: scoring normalises by the weight sum, so no
# rescaling assumption can be silently violated by retuning.
ENVIRONMENTAL_WEIGHTS: dict[str, float] = {
    "UV": 0.33,
    "Humidity": 0.22,
    "Temperature": 0.22,
    "AQI": 0.22,
}


def assert_weights_complete(weights: dict[str, float]) -> None:
    """Guard: every factor present, all non-negative, sum strictly positive."""
    missing = set(FACTOR_ORDER) - set(weights)
    if missing:
        raise ValueError(f"weight set missing factors: {sorted(missing)}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must be non-negative")
    if sum(weights.values()) <= 0:
        raise ValueError("weight sum must be positive")


assert_weights_complete(ENVIRONMENTAL_WEIGHTS)

# Guest, no profile, or unmapped concern.
DEFAULT_WEIGHTS: dict[str, float] = dict(ENVIRONMENTAL_WEIGHTS)


# --------------------------------------------------------------------------
# Concern archetypes
# --------------------------------------------------------------------------
# Five archetypes grouping the fourteen Scenario Library concerns. Membership is
# assigned from the evidence layer (which factors have cells, and their max
# risk); the penalty magnitudes are expert priors.
#
# Why not derived from library risk: mean library risk is confounded by
# editorial cell coverage. Nine concern x factor pairs are written for harsh
# bands only -- heat rash has temperature cells for Hot and Extreme Heat and no
# others -- which inflates their mean relative to concerns written across all
# bands. Deriving from that would encode coverage decisions as evidence.
ARCHETYPES = ("photo_led", "sebum_led", "barrier_led", "thermal_humid", "neutral")

DEFAULT_ARCHETYPE = "neutral"

CONCERN_ARCHETYPE: dict[str, str] = {
    # -- Scenario Library slugs (canonical) --
    "melasma": "photo_led",
    "uneven_skin_tone_tan": "photo_led",
    "dark_marks_post_acne_pih": "photo_led",
    "premature_aging_sun_damage": "photo_led",
    "vitiligo_depigmented_skin": "photo_led",
    "acne": "sebum_led",
    "oily_skin": "sebum_led",
    "dryness": "barrier_led",
    "eczema": "barrier_led",
    "heat_rash_prickly_heat": "thermal_humid",
    "fungal_infection_sweat_folds": "thermal_humid",
    # No evidenced environmental lean: keloid is tension/genetics/TGF-beta
    # driven; hair shedding is androgenetic or nutritional; periorbital
    # darkness is dominated by structural and genetic factors.
    "keloid_scar_care": "neutral",
    "hair_scalp_shedding": "neutral",
    "dark_circles_periorbital": "neutral",
    # -- legacy profile slugs --
    "dullness": "photo_led",
    "tan": "photo_led",
    "pigmentation": "photo_led",
    "aging": "photo_led",
    "redness": "barrier_led",
    "sensitivity": "barrier_led",
}

LIBRARY_CONCERN_SLUGS: frozenset[str] = frozenset({
    "acne", "dark_circles_periorbital", "dark_marks_post_acne_pih", "dryness",
    "eczema", "fungal_infection_sweat_folds", "hair_scalp_shedding",
    "heat_rash_prickly_heat", "keloid_scar_care", "melasma", "oily_skin",
    "premature_aging_sun_damage", "uneven_skin_tone_tan",
    "vitiligo_depigmented_skin",
})


def unmapped_concern_slugs() -> set[str]:
    """Library concerns with no archetype assignment. Must be empty."""
    return set(LIBRARY_CONCERN_SLUGS) - set(CONCERN_ARCHETYPE)


# Retained for callers still passing legacy profile slugs.
CONCERN_V4_MAP: dict[str, str] = dict(CONCERN_ARCHETYPE)

SKIN_V4_KEYS = frozenset({"dry", "oily", "combination", "normal", "sensitive"})


# --------------------------------------------------------------------------
# Penalty tables
# --------------------------------------------------------------------------
# Concern penalty: indexed by archetype, factor and band key. Penalties are
# assigned ONLY to bands on the tail the mechanism implicates. A weight
# multiplies a band score, and band scores are symmetric around each optimum,
# so a weight can express how much a factor matters but never which tail hurts.
# A dryness profile must not be penalised in saturated air; a heat-rash profile
# must not be penalised at 10 degC. Only a band-indexed table can say that.
_BUILTIN_CONCERN_PENALTY: dict[str, dict[str, dict[str, int]]] = {
    "photo_led": {
        "UV": {"moderate": 1, "high": 3, "very_high": 6, "extreme": 8},
        "Temperature": {"warm": 1, "hot": 3, "extreme_heat": 4},
        "AQI": {"moderate": 1, "poor": 2, "very_poor": 3, "severe": 4},
        "Humidity": {},
    },
    "sebum_led": {
        "Humidity": {"high": 2, "very_high": 4, "extreme": 5},
        "Temperature": {"warm": 2, "hot": 4, "extreme_heat": 5},
        "AQI": {"moderate": 1, "poor": 2, "very_poor": 3, "severe": 4},
        "UV": {"very_high": 1, "extreme": 1},
    },
    "barrier_led": {
        "Humidity": {"low": 2, "very_low": 5, "critical_low": 7},
        "Temperature": {"cool": 1, "cold": 3, "extreme_cold": 5, "hot": 2, "extreme_heat": 3},
        "AQI": {"moderate": 1, "poor": 2, "very_poor": 3, "severe": 4},
        "UV": {"high": 1, "very_high": 2, "extreme": 2},
    },
    "thermal_humid": {
        "Temperature": {"warm": 2, "hot": 5, "extreme_heat": 6},
        "Humidity": {"high": 2, "very_high": 5, "extreme": 6},
        "AQI": {"moderate": 1, "poor": 1, "very_poor": 2, "severe": 2},
        "UV": {},
    },
    "neutral": {"UV": {}, "Humidity": {}, "Temperature": {}, "AQI": {}},
}

# Skin penalty: zero-referenced on NORMAL skin. Normal is not unaffected by
# adverse conditions -- it takes the band-point reduction like everyone else.
# These values are the differential above normal only. A non-zero normal row
# would charge the same harm twice, since band points already encode harm to
# ordinary skin.
#
# The `sensitive` scheme is deliberately narrow. Sensitive is the most
# over-claimed self-report in dermatology, so a broad penalty is systematically
# misapplied -- bias rather than variance, which no volume of data averages out.
# It therefore carries weight only where reactivity is evidenced (UV and
# pollution at genuinely adverse levels) and nothing on ordinary days.
_BUILTIN_SKIN_BAND_PENALTY: dict[str, dict[str, dict[str, int]]] = {
    "Humidity": {
        "critical_low": {"dry": 12, "sensitive": 2, "combination": 3},
        "very_low": {"dry": 10, "sensitive": 1, "combination": 3},
        "low": {"dry": 8, "combination": 3},
        "optimal": {},
        "high": {"oily": 8, "combination": 3},
        "very_high": {"oily": 10, "sensitive": 1, "combination": 4},
        "extreme": {"oily": 12, "sensitive": 2, "combination": 4},
    },
    "UV": {
        "low": {},
        "moderate": {},
        "high": {"sensitive": 6},
        "very_high": {"sensitive": 9, "combination": 2},
        "extreme": {"sensitive": 10, "combination": 2},
    },
    "AQI": {
        "good": {},
        "satisfactory": {"oily": 2},
        "moderate": {"dry": 2, "oily": 3, "sensitive": 4, "combination": 2},
        "poor": {"dry": 2, "oily": 4, "sensitive": 6, "combination": 3},
        "very_poor": {"dry": 2, "oily": 4, "sensitive": 6, "combination": 3},
        "severe": {"dry": 2, "oily": 4, "sensitive": 6, "combination": 3},
    },
    "Temperature": {
        "extreme_cold": {"dry": 6, "sensitive": 2, "combination": 2},
        "cold": {"dry": 4, "sensitive": 1, "combination": 2},
        "cool": {"dry": 2},
        "optimal": {},
        "warm": {"oily": 3, "sensitive": 2, "combination": 2},
        "hot": {"dry": 2, "oily": 3, "sensitive": 3, "combination": 2},
        "extreme_heat": {"dry": 2, "oily": 3, "sensitive": 3, "combination": 2},
    },
}


def _load_json_table(path: Path, builtin: dict) -> dict:
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw:
                return raw
        except (json.JSONDecodeError, OSError):
            pass
    return builtin


@lru_cache(maxsize=1)
def load_skin_band_penalty() -> dict[str, dict[str, dict[str, int]]]:
    return _load_json_table(_SKIN_PENALTY_JSON, _BUILTIN_SKIN_BAND_PENALTY)


@lru_cache(maxsize=1)
def load_concern_penalty() -> dict[str, dict[str, dict[str, int]]]:
    return _load_json_table(_CONCERN_PENALTY_JSON, _BUILTIN_CONCERN_PENALTY)


def reload_skin_band_penalty() -> dict[str, dict[str, dict[str, int]]]:
    load_skin_band_penalty.cache_clear()
    return load_skin_band_penalty()


def reload_concern_penalty() -> dict[str, dict[str, dict[str, int]]]:
    load_concern_penalty.cache_clear()
    return load_concern_penalty()


# NOTE: no module-level SKIN_BAND_PENALTY alias. It went stale after a reload
# cleared the cache. Call load_skin_band_penalty().


MODE_THRESHOLDS: list[tuple[int, str]] = [
    (85, "Paradise Mode"),
    (70, "Smooth Sailing"),
    (55, "Guard Up"),
    (40, "Battle Stations"),
    (25, "Hostile Mode"),
    (0, "Code Red"),
]
