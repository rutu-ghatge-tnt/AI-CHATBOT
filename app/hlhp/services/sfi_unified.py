"""
Unified HLHP SFI — single entry point for V4 scoring across Fun surfaces.

All production Fun paths (scan Hello orb, /api/v2/today, city chart, timeline,
plan week, week-ahead) must call ``resolve_sfi`` so scores stay additive-V4-
consistent. Dominant factor is metadata only; there is no W_DOM reweighting.
"""

from __future__ import annotations

from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, UserProfile
from app.hlhp.services.scenario_engine import (
    lookup_age_rule,
    lookup_gender_rule,
    resolve_library_concerns,
    resolve_life_stage,
)
from app.hlhp.services.v4_scoring_engine import V4Evaluation, evaluate_v4, mode_for_sfi

COMFORT_SFI_THRESHOLD = 75

_FACTOR_TO_DRIVER_KEY = {
    "Temperature": "temp",
    "UV": "uv",
    "Humidity": "humidity",
    "AQI": "aqi",
}

# Profile age brackets → Scenario Library v3.6 age modifier bands.
_AGE_BRACKET_TO_LIBRARY: dict[AgeBracket, str] = {
    AgeBracket.AGE_18_24: "Young Adult",
    AgeBracket.AGE_25_30: "Young Adult",
    AgeBracket.AGE_31_40: "Adult",
    AgeBracket.AGE_41_50: "Mature",
    AgeBracket.AGE_50_PLUS: "Senior",
}


def _gender_risk_delta(profile: UserProfile | None, *, guest_mode: bool) -> float:
    if not profile or guest_mode:
        return 0.0
    store = get_scenario_store()
    life_stage = resolve_life_stage(profile)
    concerns = resolve_library_concerns(profile, guest_mode)
    concern = concerns[0] if concerns else "Acne"
    rule = lookup_gender_rule(store, life_stage, concern)
    if rule and isinstance(rule.get("risk_delta"), (int, float)):
        return float(rule["risk_delta"])
    return 0.0


def _age_risk_delta(profile: UserProfile | None, *, guest_mode: bool) -> float:
    if not profile or guest_mode or not profile.age_bracket:
        return 0.0
    age_band = _AGE_BRACKET_TO_LIBRARY.get(profile.age_bracket)
    if not age_band:
        return 0.0
    store = get_scenario_store()
    concerns = resolve_library_concerns(profile, guest_mode)
    concern = concerns[0] if concerns else "Acne"
    rule = lookup_age_rule(store, age_band, concern)
    if rule and isinstance(rule.get("risk_delta"), (int, float)):
        return float(rule["risk_delta"])
    return 0.0


def resolve_sfi(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    surge: bool = False,
) -> V4Evaluation:
    """Authoritative SFI for all HLHP surfaces."""
    return evaluate_v4(
        env,
        profile,
        guest_mode=guest_mode,
        surge=surge,
        gender_risk_delta=_gender_risk_delta(profile, guest_mode=guest_mode),
        age_risk_delta=_age_risk_delta(profile, guest_mode=guest_mode),
    )


def outdoor_ok_from_env(
    env: EnvironmentalData,
    profile: UserProfile | None = None,
    *,
    guest_mode: bool = True,
) -> tuple[int, str]:
    """V4 headline SFI + mode label — replaces legacy Outdoor-OK composite."""
    eval_ = resolve_sfi(env, profile, guest_mode=guest_mode)
    return eval_.headline_sfi, eval_.mode


def outdoor_band_for_score(score: int) -> str:
    return mode_for_sfi(int(score))


def headline_sfi(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    surge: bool = False,
) -> int:
    return resolve_sfi(env, profile, guest_mode=guest_mode, surge=surge).headline_sfi


def dominant_driver_key(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    outdoor_score_avg: float | None = None,
) -> str | None:
    """Recap / log driver key from V4 evaluation."""
    if outdoor_score_avg is not None and outdoor_score_avg >= COMFORT_SFI_THRESHOLD:
        return "comfort"
    eval_ = resolve_sfi(env, profile, guest_mode=guest_mode)
    if eval_.headline_sfi >= COMFORT_SFI_THRESHOLD:
        return "comfort"
    return _FACTOR_TO_DRIVER_KEY.get(eval_.dominant_factor, "comfort")
