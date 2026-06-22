from datetime import datetime, timezone

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.night_gate import apply_night_gate
from app.hlhp.core.season import indian_season
from app.hlhp.data.thresholds import SEVERITY_BANDS
from app.hlhp.evidence.response import evidence_cards
from app.hlhp.evidence.selector import select_evidence_bundle
from app.hlhp.evidence.steps import build_protection_steps
from app.hlhp.models.alert import AlertResponse
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.score import SeverityBand, SkinScore
from app.hlhp.services.scenario_matcher import match_scenario
from app.hlhp.services.scoring_engine import (
    _apply_overrides,
    calculate_burn_time,
    get_spf_reapply_interval,
)

_DEFAULT_KEY_DONT = "Do not skip SPF or barrier support when conditions are unstable."
_DEFAULT_EVENING = "Gentle cleanse -> targeted treatment -> barrier moisturizer."
_DEFAULT_WEEKLY = "Use one recovery mask and one gentle exfoliation session weekly."


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
    return {
        "uv_index": "UV",
        "temperature": "temperature",
        "aqi": "air quality",
        "humidity": "humidity",
    }.get(name, name)


def _build_compact_headline(score: SkinScore, first_step_action: str) -> str:
    dominant = _friendly_factor_name(score.dominant_threat)
    secondary = ", ".join(_friendly_factor_name(s) for s in score.secondary_threats[:2])
    risk_part = f"{dominant} is the main risk"
    if secondary:
        risk_part += f" with pressure from {secondary}"
    action = first_step_action.rstrip(". ").strip()
    return f"{risk_part[0].upper() + risk_part[1:]}. {action}."


def generate_alert(env: EnvironmentalData, score: SkinScore) -> AlertResponse:
    bands = bucketize_environment(env)
    season = indian_season()
    bundle = select_evidence_bundle(env, guest_mode=True)
    primary = bundle.primary

    if primary is None:
        raise RuntimeError("HLHP evidence store returned no matching row for current environment")

    finding = primary.finding
    l1 = primary.l1_text
    steps = build_protection_steps(finding, env)
    l1, steps, guest_nudge = apply_night_gate(
        uv_index=env.uv_index, l1=l1, steps=steps, guest_mode=True
    )

    whats_happening = l1 + (guest_nudge or "")
    alert_body = (
        f"UV {env.uv_index}, temp {round(env.temperature_c, 1)}C, "
        f"AQI {env.aqi}, humidity {round(env.humidity_pct)}% — "
        f"{finding.factor} alert ({finding.id})."
    )

    science_fact = _interpolate(primary.science_fact, env, score)
    science_source = primary.science_source

    scenario_code = finding.id
    scenario_number = finding.row_number

    color, icon = _get_color_and_icon(score.band)
    _, _, _, health_advisory = _apply_overrides(score.band_raw, score.factors, env)
    compact_headline = f"{icon} {_build_compact_headline(score, steps[0].action)}"

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
        scenario_number=scenario_number,
        health_advisory=health_advisory,
        color_code=color,
        icon=icon,
        generated_at=now.isoformat(),
        data_freshness_minutes=freshness,
        weather_api_url=env.weather_api_url,
        raw_weather_payload=env.raw_weather_payload,
        profile_mode="guest",
        indian_season=season,
        environment_bands={
            "uvi": bands.uvi,
            "temperature": bands.temperature,
            "humidity": bands.humidity,
            "aqi": bands.aqi,
        },
        **evidence_cards(bundle),
    )
