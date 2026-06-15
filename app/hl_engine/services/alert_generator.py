from datetime import datetime, timezone

from app.hl_engine.data.scenarios import SCENARIOS, lookup_l2
from app.hl_engine.data.science_tips import pick as pick_science_tip
from app.hl_engine.data.thresholds import SCENARIO_THRESHOLDS, SEVERITY_BANDS
from app.hl_engine.models.alert import AlertResponse, ProtectionStep
from app.hl_engine.models.environmental import EnvironmentalData
from app.hl_engine.models.score import SeverityBand, SkinScore
from app.hl_engine.services.scenario_matcher import match_scenario
from app.hl_engine.services.scoring_engine import (
    _apply_overrides,
    calculate_burn_time,
    get_spf_reapply_interval,
)

_DEFAULT_KEY_DONT = "Do not skip SPF or barrier support when conditions are unstable."
_DEFAULT_EVENING = "Gentle cleanse -> targeted treatment -> barrier moisturizer."
_DEFAULT_WEEKLY = "Use one recovery mask and one gentle exfoliation session weekly."
_SERUM_ACTION = "Use an antioxidant or niacinamide support serum"
_SERUM_REASON = "Helps defend against oxidative load from UV and pollution"


def _condition_tags(env: EnvironmentalData) -> list[str]:
    """Live weather tags for science tips — not the scenario taxonomy label."""
    t = SCENARIO_THRESHOLDS
    tags = []
    if env.uv_index >= t["uvi_high"]:
        tags.append("uv_high")
    if env.aqi > t["aqi_high"]:
        tags.append("aqi_high")
    if env.temperature_c >= t["temp_high"]:
        tags.append("temp_high")
    if env.humidity_pct < 40:
        tags.append("humidity_low")
    elif env.humidity_pct >= t["humidity_high"]:
        tags.append("humidity_high")
    return tags


def _science_pick_tags(env: EnvironmentalData, score: SkinScore) -> list[str]:
    """Pick science-tip tags from actual readings; never a stale scenario label."""
    tags = _condition_tags(env)
    if tags:
        return tags
    t = SCENARIO_THRESHOLDS
    if score.dominant_threat == "temperature" and env.temperature_c >= 27:
        return ["temp_high"]
    if score.dominant_threat == "uv_index" and env.uv_index >= 2:
        return ["uv_high"]
    if score.dominant_threat == "aqi":
        return ["aqi_high"]
    if score.dominant_threat == "humidity":
        if env.humidity_pct >= t["humidity_high"]:
            return ["humidity_high"]
        if env.humidity_pct < 40:
            return ["humidity_low"]
    return ["uv_high"]


def _get_color_and_icon(band: SeverityBand) -> tuple[str, str]:
    for _, _, band_name, color, icon in SEVERITY_BANDS:
        if band_name == band.value:
            return color, icon
    return "#F39C12", "🛡️"


def _interpolate(template: str, env: EnvironmentalData, score: SkinScore) -> str:
    try:
        return template.format(
            uv=env.uv_index,
            temp=round(env.temperature_c, 1),
            aqi=env.aqi,
            humidity=round(env.humidity_pct),
            score=score.total,
            burn_time=calculate_burn_time(env.uv_index) or "N/A",
            spf_interval=get_spf_reapply_interval(env.temperature_c),
            location=env.location_name,
            dominant_threat=score.dominant_threat,
            band=score.band.value,
        )
    except (KeyError, ValueError):
        return template


def _friendly_factor_name(name: str) -> str:
    mapping = {
        "uv_index": "UV",
        "temperature": "temperature",
        "aqi": "air quality",
        "humidity": "humidity",
    }
    return mapping.get(name, name)


def _build_compact_headline(score: SkinScore, first_step_action: str) -> str:
    dominant = _friendly_factor_name(score.dominant_threat)
    secondary = ", ".join(_friendly_factor_name(s) for s in score.secondary_threats[:2])
    risk_part = f"{dominant} is the main risk"
    if secondary:
        risk_part += f" with pressure from {secondary}"
    action = first_step_action.rstrip(". ").strip()
    return f"{risk_part[0].upper() + risk_part[1:]}. {action}."


def _moisturizer_action(env: EnvironmentalData) -> str:
    if env.humidity_pct >= SCENARIO_THRESHOLDS["humidity_high"]:
        return "Use a lightweight gel moisturizer"
    return "Use a barrier-support cream moisturizer"


def _build_protection_steps(env: EnvironmentalData, scenario: dict) -> list[ProtectionStep]:
    """Map new L2/L3 scenario copy into the legacy three-step structure."""
    l2 = lookup_l2(scenario, "normal", None)
    moisturizer = _moisturizer_action(env)
    return [
        ProtectionStep(
            step_number=1,
            action=l2,
            reason="Matches today's UV, heat, and pollution load.",
            product_category="sunscreen",
        ),
        ProtectionStep(
            step_number=2,
            action=_SERUM_ACTION,
            reason=_SERUM_REASON,
            product_category="serum",
        ),
        ProtectionStep(
            step_number=3,
            action=moisturizer,
            reason="Supports barrier while minimizing congestion risk.",
            product_category="moisturizer",
        ),
    ]


def generate_alert(env: EnvironmentalData, score: SkinScore) -> AlertResponse:
    scenario_num, scenario_code = match_scenario(env)
    scenario = SCENARIOS[scenario_num]

    color, icon = _get_color_and_icon(score.band)
    whats_happening = (
        f"Conditions in {env.location_name} increase stress from "
        f"{_friendly_factor_name(score.dominant_threat)}. {scenario['L1']}"
    )
    alert_body = (
        f"UV {env.uv_index}, temp {round(env.temperature_c, 1)}C, "
        f"AQI {env.aqi}, humidity {round(env.humidity_pct)}% indicate elevated skin stress."
    )

    steps = _build_protection_steps(env, scenario)

    tags = _science_pick_tags(env, score)
    tip = pick_science_tip(tags)
    science_fact = _interpolate(tip["fact"], env, score)
    science_source = tip["source"]

    _, _, _, health_advisory = _apply_overrides(score.band_raw, score.factors, env)
    compact_headline = _build_compact_headline(score, steps[0].action)
    compact_headline = f"{icon} {compact_headline}"

    if score.band in (SeverityBand.CODE_RED, SeverityBand.HOSTILE):
        expand_cta = "See full protection plan ->"
    elif score.band in (SeverityBand.BATTLE, SeverityBand.GUARD):
        expand_cta = "See what to do ->"
    else:
        expand_cta = "See today's routine ->"

    now = datetime.now(timezone.utc)
    freshness = int((now - env.fetched_at).total_seconds() / 60)

    return AlertResponse(
        location_name=env.location_name,
        uv_index=env.uv_index,
        temperature_c=env.temperature_c,
        aqi=env.aqi,
        humidity_pct=env.humidity_pct,
        skin_score=score,
        compact_headline=compact_headline,
        score_badge=f"{icon} {score.total}/100",
        expand_cta=expand_cta,
        whats_happening=whats_happening,
        alert_body=alert_body,
        protection_steps=steps,
        key_dont=_DEFAULT_KEY_DONT,
        evening_recovery=_DEFAULT_EVENING,
        weekly_boost=_DEFAULT_WEEKLY,
        science_fact=science_fact,
        science_source=science_source,
        scenario_code=scenario_code,
        scenario_number=scenario_num,
        health_advisory=health_advisory,
        color_code=color,
        icon=icon,
        generated_at=now.isoformat(),
        data_freshness_minutes=freshness,
        weather_api_url=env.weather_api_url,
        raw_weather_payload=env.raw_weather_payload,
    )
