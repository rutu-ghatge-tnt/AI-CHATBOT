import random
from datetime import datetime, timezone

from app.hl_engine.data.scenarios import SCENARIOS
from app.hl_engine.data.science_nuggets import SCIENCE_NUGGETS
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


def _get_color_and_icon(band: SeverityBand) -> tuple[str, str]:
    for _, _, band_name, color, icon in SEVERITY_BANDS:
        if band_name == band.value:
            return color, icon
    return "#F39C12", "🛡️"


def _select_science_nugget(env: EnvironmentalData):
    tags = []
    t = SCENARIO_THRESHOLDS
    if env.uv_index >= t["uvi_high"]:
        tags.append("uvi_high")
    if env.temperature_c >= t["temp_high"]:
        tags.append("temp_high")
    if env.aqi > t["aqi_high"]:
        tags.append("aqi_high")
    if env.humidity_pct < 30:
        tags.append("humidity_low")
    elif env.humidity_pct >= t["humidity_high"]:
        tags.append("humidity_high")
    relevant = [n for n in SCIENCE_NUGGETS if any(tag in tags for tag in n["relevant_when"])] or SCIENCE_NUGGETS
    picked = random.choice(relevant)
    return picked["fact"], picked["source"]


def _interpolate(template: str, env: EnvironmentalData, score: SkinScore) -> str:
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


def _friendly_factor_name(name: str) -> str:
    mapping = {
        "uv_index": "UV",
        "temperature": "temperature",
        "aqi": "air quality",
        "humidity": "humidity",
    }
    return mapping.get(name, name)


def _build_compact_headline(
    env: EnvironmentalData,
    score: SkinScore,
    health_advisory: str | None,
    first_step_action: str,
) -> str:
    dominant = _friendly_factor_name(score.dominant_threat)
    secondary = ", ".join(_friendly_factor_name(s) for s in score.secondary_threats[:2])
    risk_part = f"{dominant} is the main risk"
    if secondary:
        risk_part += f" with pressure from {secondary}"

    headline = (
        f"{score.band.value} ({score.total}/100): {risk_part} in {env.location_name}. "
        f"Priority now: {first_step_action}."
    )

    if health_advisory:
        headline += " Follow health advisory."

    return headline


def generate_alert(env: EnvironmentalData, score: SkinScore) -> AlertResponse:
    scenario_num, scenario_code = match_scenario(env)
    scenario = SCENARIOS[scenario_num]

    color, icon = _get_color_and_icon(score.band)
    whats_happening = _interpolate(scenario["whats_happening"], env, score)
    compact_headline = _interpolate(scenario["compact_headline"], env, score)
    alert_body = _interpolate(scenario["alert_body"], env, score)
    key_dont = _interpolate(scenario["key_dont"], env, score)

    spf_interval = get_spf_reapply_interval(env.temperature_c)
    steps = []
    for idx, step in enumerate(scenario["steps"], start=1):
        steps.append(
            ProtectionStep(
                step_number=idx,
                action=step["action"].format(spf_interval=spf_interval),
                reason=step["reason"],
                product_category=step["product_category"],
            )
        )

    science_fact_raw, science_source = _select_science_nugget(env)
    science_fact = _interpolate(science_fact_raw, env, score)

    _, _, _, health_advisory = _apply_overrides(score.band_raw, score.factors, env)
    if steps:
        compact_headline = _build_compact_headline(
            env=env,
            score=score,
            health_advisory=health_advisory,
            first_step_action=steps[0].action,
        )

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
        key_dont=key_dont,
        evening_recovery=scenario["evening_recovery"],
        weekly_boost=scenario["weekly_boost"],
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

