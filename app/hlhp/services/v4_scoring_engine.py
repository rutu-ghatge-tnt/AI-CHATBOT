"""
HLHP deterministic scoring engine — canonical SFI for all Fun surfaces.

Six stages
----------
1. Band          each reading to a named band carrying 0-25 points
2. Weight        skin-relevance-weighted mean, rescaled to 0-100
3. Override      cap at 54 when any factor bottoms out
4. Concern       one-sided penalty by archetype, factor and band
5. Skin type     penalty by skin type, factor and band
6. Mode          named severity band for the headline score

Formula::

    ESFI = min( 100 * sum(w_f * p_f) / (25 * sum(w_f)) , 54 if any p_f == 0 )
    PSFI = clip( ESFI - rho_concern - rho_skin , 0 , 100 )

Both penalties are non-negative, so PSFI <= ESFI is a property of the
arithmetic rather than a rule the code enforces.

Not in the score
----------------
Life stage and the daily feeling log. Both act on cell risk and copy register
instead -- see ``sfi_unified``. Bands, points and band keys are canonical from
the Scenario Library; ``conformance_test.py`` asserts they stay in step.

``dominant_factor`` (lowest points) is UI-only and reweights nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.hlhp.data.v4_scoring_data import (
    CONCERN_ARCHETYPE,
    DEFAULT_ARCHETYPE,
    ENVIRONMENTAL_WEIGHTS,
    FACTOR_ORDER,
    MODE_THRESHOLDS,
    SKIN_V4_KEYS,
    BandRow,
    load_concern_penalty,
    load_skin_band_penalty,
)
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile

ImpactLevel = Literal["Low", "Medium", "High"]
SceneKey = Literal["storm", "snow", "windy", "haze", "heat", "rain", "clear"]

# Display ranges, mirroring Scenario Library sheet `2. Bands Reference`.
BAND_RANGES: dict[str, dict[str, str]] = {
    "Temperature": {
        "extreme_cold": "<5\u00b0C", "cold": "5-14\u00b0C", "cool": "15-19\u00b0C",
        "optimal": "20-27\u00b0C", "warm": "28-34\u00b0C", "hot": "35-42\u00b0C",
        "extreme_heat": ">42\u00b0C",
    },
    "AQI": {
        "good": "0-50", "satisfactory": "51-100", "moderate": "101-200",
        "poor": "201-300", "very_poor": "301-400", "severe": ">400",
    },
    "UV": {
        "low": "0-2", "moderate": "3-5", "high": "6-7",
        "very_high": "8-10", "extreme": "11+",
    },
    "Humidity": {
        "critical_low": "<10%", "very_low": "10-19%", "low": "20-39%",
        "optimal": "40-60%", "high": "61-79%", "very_high": "80-89%",
        "extreme": ">90%",
    },
}


@dataclass(frozen=True)
class V4Band:
    factor: str
    key: str
    label: str
    points: int
    level: ImpactLevel
    value: float
    dominant: bool = False


@dataclass(frozen=True)
class V4Evaluation:
    bands: dict[str, V4Band]
    drivers: list[V4Band]
    environmental_sfi: int
    personal_sfi: int | None
    headline_sfi: int
    mode: str
    dominant_factor: str
    scene: SceneKey
    guest_mode: bool
    archetype: str | None = None
    rho_concern: int = 0
    rho_skin: int = 0
    esfi_raw: float = 0.0
    override_active: bool = False


# --------------------------------------------------------------------------
# Stage 1 — banding (canonical from Scenario Library `2. Bands Reference`)
# --------------------------------------------------------------------------

def _band_temp(c: float) -> BandRow:
    if c < 5:
        return {"key": "extreme_cold", "label": "Extreme Cold", "points": 0}
    if c < 15:
        return {"key": "cold", "label": "Cold", "points": 5}
    if c <= 19:
        return {"key": "cool", "label": "Cool", "points": 12}
    if c <= 27:
        return {"key": "optimal", "label": "Optimal", "points": 25}
    if c <= 34:
        return {"key": "warm", "label": "Warm", "points": 12}
    if c <= 42:
        return {"key": "hot", "label": "Hot", "points": 5}
    return {"key": "extreme_heat", "label": "Extreme Heat", "points": 0}


def _band_uv(uvi: float) -> BandRow:
    # No cliff: the earlier 12 -> 2 drop between UVI 7 and 8 had no dose-response
    # basis and compressed the range most of urban India occupies year-round.
    if uvi <= 2:
        return {"key": "low", "label": "Low", "points": 25}
    if uvi <= 5:
        return {"key": "moderate", "label": "Moderate", "points": 18}
    if uvi <= 7:
        return {"key": "high", "label": "High", "points": 11}
    if uvi <= 10:
        return {"key": "very_high", "label": "Very High", "points": 5}
    return {"key": "extreme", "label": "Extreme", "points": 0}


def _band_humidity(rh: float) -> BandRow:
    # Asymmetric by design. High humidity is barrier-protective for intact skin;
    # its real harms (miliaria, intertrigo, occlusion) belong to the concern
    # layer, not the base score. Only the dry tail reaches zero.
    if rh < 10:
        return {"key": "critical_low", "label": "Critical Low", "points": 0}
    if rh < 20:
        return {"key": "very_low", "label": "Very Low", "points": 5}
    if rh <= 39:
        return {"key": "low", "label": "Low", "points": 12}
    if rh <= 60:
        return {"key": "optimal", "label": "Optimal", "points": 25}
    if rh <= 79:
        return {"key": "high", "label": "High", "points": 15}
    if rh <= 89:
        return {"key": "very_high", "label": "Very High", "points": 9}
    return {"key": "extreme", "label": "Extreme", "points": 5}


def _band_aqi(aqi: int) -> BandRow:
    if aqi <= 50:
        return {"key": "good", "label": "Good", "points": 25}
    if aqi <= 100:
        return {"key": "satisfactory", "label": "Satisfactory", "points": 18}
    if aqi <= 200:
        return {"key": "moderate", "label": "Moderate", "points": 10}
    if aqi <= 300:
        return {"key": "poor", "label": "Poor", "points": 5}
    if aqi <= 400:
        return {"key": "very_poor", "label": "Very Poor", "points": 2}
    return {"key": "severe", "label": "Severe", "points": 0}


_BAND_FN = {
    "Temperature": lambda env: _band_temp(env.temperature_c),
    "UV": lambda env: _band_uv(env.uv_index),
    "Humidity": lambda env: _band_humidity(env.humidity_pct),
    "AQI": lambda env: _band_aqi(int(env.aqi)),
}

_FACTOR_VALUE = {
    "Temperature": lambda env: env.temperature_c,
    "UV": lambda env: env.uv_index,
    "Humidity": lambda env: env.humidity_pct,
    "AQI": lambda env: float(env.aqi),
}


def points_to_level(points: int) -> ImpactLevel:
    if points >= 20:
        return "Low"
    if points >= 10:
        return "Medium"
    return "High"


def clamp_sfi(value: float) -> int:
    return max(0, min(100, round(value)))


def mode_for_sfi(sfi: int) -> str:
    for threshold, name in MODE_THRESHOLDS:
        if sfi >= threshold:
            return name
    return "Code Red"


def band_map(env: EnvironmentalData) -> dict[str, V4Band]:
    out: dict[str, V4Band] = {}
    for factor in FACTOR_ORDER:
        row = _BAND_FN[factor](env)
        out[factor] = V4Band(
            factor=factor,
            key=row["key"],
            label=row["label"],
            points=row["points"],
            level=points_to_level(row["points"]),
            value=_FACTOR_VALUE[factor](env),
        )
    return out


def dominant_factor(bands: dict[str, V4Band]) -> str:
    """Lowest points wins; ties resolve Temperature -> UV -> Humidity -> AQI."""
    best = FACTOR_ORDER[0]
    best_pts = bands[best].points
    for factor in FACTOR_ORDER[1:]:
        if bands[factor].points < best_pts:
            best, best_pts = factor, bands[factor].points
    return best


# --------------------------------------------------------------------------
# Stage 2 — weighted mean
# --------------------------------------------------------------------------

def weighted_score(bands: dict[str, V4Band], weights: dict[str, float]) -> float:
    """Weighted mean of band points rescaled to 0-100.

    Normalised by the weight sum, so weights need not total 1 and no scaling
    assumption can be silently violated by retuning.
    """
    den = 25.0 * sum(weights.values())
    if den <= 0:
        return 0.0
    return 100.0 * sum(weights[f] * bands[f].points for f in weights) / den


# --------------------------------------------------------------------------
# Stage 3 — anti-masking override
# --------------------------------------------------------------------------
# Symmetric: ANY factor in its 0-point band caps the score. Yields an
# unqualified guarantee -- exists f : p_f = 0 => ESFI <= 54 -- with no carve-out
# to defend. The 0-point bands are by construction the hostile extreme of each
# factor, so nothing is capped that the library does not already call maximally
# damaging. Humidity Extreme no longer reaches 0 and therefore cannot trip it;
# Humidity Critical Low still does, which is where the acute barrier harm is.
HAZARD_ZERO_BANDS: frozenset[tuple[str, str]] = frozenset({
    ("UV", "extreme"),
    ("AQI", "severe"),
    ("Temperature", "extreme_heat"),
    ("Temperature", "extreme_cold"),
    ("Humidity", "critical_low"),
})

# Top of Battle Stations. NOT empirically derived -- flagged for calibration.
OVERRIDE_CEILING = 54


def hazard_override_active(bands: dict[str, V4Band]) -> bool:
    """True when any factor has bottomed out (0 points)."""
    return any(b.points == 0 for b in bands.values())


def environmental_sfi(bands: dict[str, V4Band]) -> int:
    raw = clamp_sfi(weighted_score(bands, ENVIRONMENTAL_WEIGHTS))
    if hazard_override_active(bands):
        return min(raw, OVERRIDE_CEILING)
    return raw


# --------------------------------------------------------------------------
# Stages 4 and 5 — penalties
# --------------------------------------------------------------------------

def resolve_concern_archetype(profile: UserProfile | None) -> str:
    """Map a profile concern (library slug or legacy slug) to an archetype."""
    if not profile or not profile.primary_concern:
        return DEFAULT_ARCHETYPE
    slug = str(profile.primary_concern.value).strip().lower()
    return CONCERN_ARCHETYPE.get(slug, DEFAULT_ARCHETYPE)


# Backwards-compatible alias.
resolve_v4_concern = resolve_concern_archetype


def resolve_v4_skin(profile: UserProfile | None) -> str:
    if not profile or not profile.skin_type:
        return "normal"
    skin = str(profile.skin_type.value).lower()
    return skin if skin in SKIN_V4_KEYS else "normal"


def concern_penalty(bands: dict[str, V4Band], archetype: str) -> int:
    """One-sided penalty: only bands on the tail the mechanism implicates."""
    table = load_concern_penalty().get(archetype, {})
    return sum(int(table.get(f, {}).get(b.key, 0)) for f, b in bands.items())


def skin_penalty(bands: dict[str, V4Band], skin: str) -> int:
    """Differential above normal skin. Normal is the zero reference."""
    key = skin.lower() if skin.lower() in SKIN_V4_KEYS else "normal"
    table = load_skin_band_penalty()
    return sum(int(table.get(f, {}).get(b.key, {}).get(key, 0)) for f, b in bands.items())


def personal_sfi(bands: dict[str, V4Band], archetype: str, skin: str) -> int:
    """Environmental score less both personalisation differentials.

    Both penalties are non-negative, so this can never exceed the environmental
    score. That is a property of the arithmetic, not an enforced rule.
    """
    return clamp_sfi(
        environmental_sfi(bands) - concern_penalty(bands, archetype) - skin_penalty(bands, skin)
    )


# --------------------------------------------------------------------------
# Scene (visual only)
# --------------------------------------------------------------------------

def scene_key(env: EnvironmentalData, *, surge: bool = False) -> SceneKey:
    if surge:
        return "storm"
    if env.temperature_c <= 8:
        return "snow"
    if getattr(env, "wind_kmh", 0) and env.wind_kmh >= 30:
        return "windy"
    if env.aqi >= 201:
        return "haze"
    if env.temperature_c >= 35:
        return "heat"
    if env.humidity_pct >= 61:
        return "rain"
    return "clear"


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------

def evaluate_v4(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    surge: bool = False,
) -> V4Evaluation:
    bands = band_map(env)
    dom = dominant_factor(bands)
    raw = weighted_score(bands, ENVIRONMENTAL_WEIGHTS)
    env_sfi = environmental_sfi(bands)

    personal: int | None = None
    archetype: str | None = None
    rc = rs = 0
    headline = env_sfi

    if not guest_mode and profile is not None:
        archetype = resolve_concern_archetype(profile)
        skin = resolve_v4_skin(profile)
        rc = concern_penalty(bands, archetype)
        rs = skin_penalty(bands, skin)
        personal = clamp_sfi(env_sfi - rc - rs)
        headline = personal

    drivers = [
        V4Band(
            factor=bands[f].factor, key=bands[f].key, label=bands[f].label,
            points=bands[f].points, level=bands[f].level, value=bands[f].value,
            dominant=(f == dom),
        )
        for f in FACTOR_ORDER
    ]

    return V4Evaluation(
        bands=bands,
        drivers=drivers,
        environmental_sfi=env_sfi,
        personal_sfi=personal,
        headline_sfi=headline,
        mode=mode_for_sfi(headline),
        dominant_factor=dom,
        scene=scene_key(env, surge=surge),
        guest_mode=guest_mode,
        archetype=archetype,
        rho_concern=rc,
        rho_skin=rs,
        esfi_raw=round(raw, 2),
        override_active=hazard_override_active(bands),
    )


def to_driver_states(eval_: V4Evaluation) -> list[dict[str, Any]]:
    """Bridge bands to scenario_engine DriverState dicts for alert lookup."""
    names = {"Temperature": "Heat", "UV": "UV", "Humidity": "Humidity", "AQI": "Air (AQI)"}
    keys = {"Temperature": "temp", "UV": "uv", "Humidity": "humidity", "AQI": "aqi"}
    return [
        {
            "factor": d.factor,
            "key": keys[d.factor],
            "name": names[d.factor],
            "value": d.value,
            "band_label": d.label,
            "band_key": d.key,
            "band_range": BAND_RANGES.get(d.factor, {}).get(d.key, ""),
            "points": d.points,
        }
        for d in eval_.drivers
    ]


# NOTE: the feeling log does NOT modify the SFI. The index reads the
# environment; a self-reported skin state is an outcome signal and the primary
# input to the calibration programme, not a term in the score. Any module
# importing a feeling-log SFI delta is wiring a path that was never part of
# `resolve_sfi`, and should surface the log through alert level and copy.
