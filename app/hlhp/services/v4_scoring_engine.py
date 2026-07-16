"""
HLHP V4 deterministic scoring engine — canonical Fun / scan / city-chart SFI.

**Canonical formula (additive V4):**
- Environmental SFI = sum of four factor band points (Temperature, UV, Humidity, AQI),
  each 0–25 → total 0–100.
- Personal SFI = concern-weighted average of those points, minus skin-band penalties
  (and small gender/age deltas when profile is present).
- Headline SFI = personal when logged-in with profile; else environmental.

`dominant_factor` (lowest points) is **UI-only** — it does not reweight the score.
V7 reference `W_DOM=0.6` blend is **not** used in production.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.hlhp.data.v4_scoring_data import (
    CONCERN_V4_MAP,
    CONCERN_WEIGHTS,
    DEFAULT_WEIGHTS,
    FACTOR_ORDER,
    MODE_THRESHOLDS,
    SKIN_V4_KEYS,
    load_skin_band_penalty,
    BandRow,
)
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile

ImpactLevel = Literal["Low", "Medium", "High"]
SceneKey = Literal["storm", "snow", "windy", "haze", "heat", "rain", "clear"]


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
class V4Sfi:
    environmental: int
    personal: int | None
    headline: int


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


def _band_temp(c: float) -> BandRow:
    if c < 15:
        return {"key": "cold", "label": "Cold", "points": 8}
    if c <= 19:
        return {"key": "cool", "label": "Cool", "points": 12}
    if c <= 27:
        return {"key": "optimal", "label": "Optimal", "points": 25}
    if c <= 34:
        return {"key": "warm", "label": "Warm", "points": 12}
    if c <= 42:
        return {"key": "hot", "label": "Hot", "points": 5}
    return {"key": "extreme", "label": "Extreme", "points": 0}


def _band_uv(uvi: float) -> BandRow:
    if uvi <= 2:
        return {"key": "low", "label": "Low", "points": 25}
    if uvi <= 5:
        return {"key": "moderate", "label": "Moderate", "points": 18}
    if uvi <= 7:
        return {"key": "high", "label": "High", "points": 12}
    if uvi <= 10:
        return {"key": "very_high", "label": "Very High", "points": 2}
    return {"key": "extreme", "label": "Extreme", "points": 0}


def _band_humidity(rh: float) -> BandRow:
    if rh < 20:
        return {"key": "very_low", "label": "Very Low", "points": 5}
    if rh <= 39:
        return {"key": "low", "label": "Low", "points": 12}
    if rh <= 60:
        return {"key": "optimal", "label": "Optimal", "points": 25}
    if rh <= 79:
        return {"key": "high", "label": "High", "points": 12}
    if rh <= 89:
        return {"key": "very_high", "label": "Very High", "points": 5}
    return {"key": "extreme", "label": "Extreme", "points": 0}


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


def scene_key(env: EnvironmentalData, *, surge: bool = False) -> SceneKey:
    if surge:
        return "storm"
    if env.temperature_c <= 8:
        return "snow"
    if env.wind_kmh >= 30:
        return "windy"
    if env.aqi >= 201:
        return "haze"
    if env.temperature_c >= 35:
        return "heat"
    if env.humidity_pct >= 61:
        return "rain"
    return "clear"


def resolve_v4_concern(profile: UserProfile | None) -> str:
    if not profile or not profile.primary_concern:
        return "Acne"
    slug = profile.primary_concern.value
    return CONCERN_V4_MAP.get(slug, "Acne")


def resolve_v4_skin(profile: UserProfile | None) -> str:
    if not profile or not profile.skin_type:
        return "normal"
    skin = profile.skin_type.value.lower()
    return skin if skin in SKIN_V4_KEYS else "normal"


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
    """Lowest points wins; ties: Temperature → UV → Humidity → AQI."""
    best = FACTOR_ORDER[0]
    best_pts = bands[best].points
    for factor in FACTOR_ORDER[1:]:
        pts = bands[factor].points
        if pts < best_pts:
            best, best_pts = factor, pts
    return best


def environmental_sfi(bands: dict[str, V4Band]) -> int:
    return sum(b.points for b in bands.values())


def personal_sfi(
    bands: dict[str, V4Band],
    concern: str,
    skin: str,
    *,
    gender_risk_delta: int | float = 0,
    age_risk_delta: int | float = 0,
) -> int:
    wt = CONCERN_WEIGHTS.get(concern, DEFAULT_WEIGHTS)
    num = sum(wt[f] * bands[f].points for f in wt)
    den = 25 * sum(wt.values())
    base = 100 * num / den if den else 0.0

    skin_key = skin.lower() if skin.lower() in SKIN_V4_KEYS else "normal"
    pen = 0
    penalty_table = load_skin_band_penalty()
    for factor, band in bands.items():
        band_key = band.key
        if factor == "Temperature" and band_key == "extreme":
            band_key = "extreme_heat"
        factor_pen = penalty_table.get(factor, {}).get(band_key, {})
        if not factor_pen and factor == "Temperature":
            factor_pen = penalty_table.get(factor, {}).get(band.key, {})
        pen += int(factor_pen.get(skin_key, 0))

    adjusted = base - pen
    for delta in (gender_risk_delta, age_risk_delta):
        if isinstance(delta, (int, float)) and delta > 0:
            adjusted -= float(delta) * 4

    return clamp_sfi(adjusted)


def evaluate_v4(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    surge: bool = False,
    gender_risk_delta: int | float = 0,
    age_risk_delta: int | float = 0,
) -> V4Evaluation:
    bands = band_map(env)
    dom = dominant_factor(bands)
    env_sfi = environmental_sfi(bands)

    personal: int | None = None
    headline = env_sfi
    if not guest_mode and profile is not None:
        concern = resolve_v4_concern(profile)
        skin = resolve_v4_skin(profile)
        personal = personal_sfi(
            bands,
            concern,
            skin,
            gender_risk_delta=gender_risk_delta,
            age_risk_delta=age_risk_delta,
        )
        headline = personal

    drivers: list[V4Band] = []
    for factor in FACTOR_ORDER:
        b = bands[factor]
        drivers.append(
            V4Band(
                factor=b.factor,
                key=b.key,
                label=b.label,
                points=b.points,
                level=b.level,
                value=b.value,
                dominant=(factor == dom),
            )
        )

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
    )


def to_driver_states(eval_: V4Evaluation) -> list[dict[str, Any]]:
    """Bridge V4 bands to scenario_engine DriverState-compatible dicts for alert lookup."""
    names = {
        "Temperature": "Heat",
        "UV": "UV",
        "Humidity": "Humidity",
        "AQI": "Air (AQI)",
    }
    keys = {
        "Temperature": "temp",
        "UV": "uv",
        "Humidity": "humidity",
        "AQI": "aqi",
    }
    out = []
    for d in eval_.drivers:
        out.append(
            {
                "factor": d.factor,
                "key": keys[d.factor],
                "name": names[d.factor],
                "value": d.value,
                "band_label": d.label,
                "band_key": d.key,
                "band_range": "",
                "points": d.points,
            }
        )
    return out


_SYMPTOM_SFI_DELTA: dict[str, int] = {
    "normal": 0,
    "dry": -4,
    "oily": -3,
    "dull": -3,
    "breakout": -10,
    "spots": -8,
}

_EXPOSURE_SFI_DELTA: dict[str, int] = {
    "in": 0,
    "<1": -2,
    "1-3": -5,
    "3+": -9,
}


def feeling_log_sfi_adjustment(
    *,
    symptoms: list[str] | None = None,
    outdoor_exposure: str | None = None,
    notes: str | None = None,
) -> int:
    """Negative delta from today's feeling log — lowers personal/headline SFI."""
    delta = 0
    syms = [s.strip().lower().replace(" ", "_") for s in (symptoms or []) if s.strip()]
    if syms:
        if not ("normal" in syms and len(syms) == 1):
            worst = min(_SYMPTOM_SFI_DELTA.get(s, -2) for s in syms)
            delta += worst
    exp = (outdoor_exposure or "").strip()
    if exp in _EXPOSURE_SFI_DELTA:
        delta += _EXPOSURE_SFI_DELTA[exp]
    if (notes or "").strip():
        delta -= 1
    return delta
