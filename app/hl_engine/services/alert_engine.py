"""
The unified engine entry point.

Single function: evaluate(env, profile=None) → EngineResponse.

Internally it runs four passes:
  1. Score      → personalised SFI + band + dominant factor
  2. Match      → one of 16 scenarios
  3. Build Alert→ L1 (universal) + L2 (skin-type / concern) + L3 (technique)
  4. Pick Tip   → science fact whose tags overlap the day's tags
"""

from app.hl_engine.data.scenarios import lookup_l2
from app.hl_engine.data.science_tips import pick as pick_tip
from app.hl_engine.data.thresholds import SCENARIO_CUTS
from app.hl_engine.models.engine_models import (
    Alert,
    EngineResponse,
    EnvironmentalData,
    ScienceTip,
    UserProfile,
)
from app.hl_engine.services.scenario_match import match as match_scenario
from app.hl_engine.services.scoring import compute_sfi


def _condition_tags(env: EnvironmentalData) -> list[str]:
    """The day's condition tags — used to pick a relevant science tip."""
    c = SCENARIO_CUTS
    tags = []
    if env.uv_index    >= c["uvi_high"]:      tags.append("uv_high")
    if env.aqi          > c["aqi_high"]:      tags.append("aqi_high")
    if env.temperature_c >= c["temp_high"]:   tags.append("temp_high")
    if env.humidity_pct < 40:                 tags.append("humidity_low")
    elif env.humidity_pct >= c["humidity_high"]: tags.append("humidity_high")
    return tags


def _profile_summary(profile: UserProfile | None) -> str:
    if profile is None:
        return "anonymous (normal · no concern)"
    parts = []
    parts.append(profile.skin_type.value if profile.skin_type else "no skin type")
    parts.append(profile.primary_concern.value if profile.primary_concern else "no concern")
    return " · ".join(parts)


def evaluate(env: EnvironmentalData,
             profile: UserProfile | None = None) -> EngineResponse:
    """
    The single public entry point.

    Returns a full EngineResponse — score, band, scenario, L1/L2/L3 alert,
    and one science tip. Pass profile=None for the anonymous baseline.
    """
    # 1. Score
    sfi, band_name, band_color, is_personalized, breakdown, dominant = \
        compute_sfi(env, profile)

    # 2. Match scenario
    scenario = match_scenario(env)

    # 3. Build the alert
    skin_type = profile.skin_type.value if (profile and profile.skin_type) else None
    concern   = profile.primary_concern.value if (profile and profile.primary_concern) else None

    alert = Alert(
        l1=scenario["L1"],
        l2=lookup_l2(scenario, skin_type, concern),
        l3=scenario["L3"],
    )

    # 4. Pick a science tip whose tags overlap the day
    tags = scenario.get("science_tags") or _condition_tags(env)
    tip_dict = pick_tip(tags)
    tip = ScienceTip(fact=tip_dict["fact"], source=tip_dict["source"])

    return EngineResponse(
        skin_friendliness_index=sfi,
        band=band_name,
        band_color=band_color,
        is_personalized=is_personalized,
        factor_breakdown=breakdown,
        location=env.location,
        readings=env,
        scenario_code=scenario["code"],
        scenario_name=scenario["name"],
        alert=alert,
        science_tip=tip,
        profile_summary=_profile_summary(profile),
    )
