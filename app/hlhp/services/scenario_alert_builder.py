"""Build v1/v2 alert responses from the scenario library only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.night_gate import apply_night_gate
from app.hlhp.core.profile_mode import profile_completeness, resolve_mode
from app.hlhp.core.season import indian_season
from app.hlhp.data.age_priorities import get_age_priority, reorder_steps_by_age
from app.hlhp.data.concern_emphasis import get_concern_key_dont
from app.hlhp.data.gender_language import apply_language_swap, get_gender_tip
from app.hlhp.data.texture_map import get_textured_product
from app.hlhp.data.thresholds import SEVERITY_BANDS
from app.hlhp.evidence.scenario_store import ScenarioStore, get_scenario_store
from app.hlhp.models.alert import AlertResponse, ProtectionStep, ScienceNuggetCard
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.personalized_alert import PersonalizedAlertResponse
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.score import SeverityBand, SkinScore
from app.hlhp.services.hair_alert_generator import generate_hair_alert
from app.hlhp.services.scenario_engine import ScenarioEvaluation, evaluate_scenario
from app.hlhp.services.scenario_steps import build_protection_steps_from_scenario
from app.hlhp.services.scoring_engine import (
    _apply_overrides,
    calculate_burn_time,
)

_DEFAULT_KEY_DONT = "Do not skip SPF or barrier support when conditions are unstable."
_DEFAULT_EVENING = "Gentle cleanse -> targeted treatment -> barrier moisturizer."
_DEFAULT_WEEKLY = "Use one recovery mask and one gentle exfoliation session weekly."


def _get_color_and_icon(band: SeverityBand) -> tuple[str, str]:
    for _, _, band_name, color, icon in SEVERITY_BANDS:
        if band_name == band.value:
            return color, icon
    return "#F39C12", "🛡️"


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


def _scenario_number(cell_id: str) -> int:
    tail = (cell_id or "").rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _scenario_cell_id(scenario: ScenarioEvaluation) -> str:
    if scenario.evidence_cell:
        return scenario.evidence_cell.id
    cell = scenario.cell or {}
    return str(cell.get("id", ""))


def _science_from_scenario(scenario: ScenarioEvaluation) -> tuple[str, str]:
    ev = scenario.evidence_cell
    if ev and ev.evidence:
        source = "|".join(ev.pmids) if ev.pmids else "SkinBB HLHP Scenario Library v3.6"
        return ev.evidence, source
    return scenario.flash_alert.l0 or scenario.flash_alert.l1, "SkinBB HLHP Scenario Library v3.6"


def _pick_scenario_nuggets(
    store: ScenarioStore,
    scenario: ScenarioEvaluation,
    user_id: Optional[str],
    *,
    count: int = 3,
) -> list[ScienceNuggetCard]:
    factor = scenario.dominant.factor
    pool = [n for n in store.nuggets if (n.get("factor") or "").lower() == factor.lower()]
    if not pool:
        pool = list(store.nuggets)
    if not pool:
        return []
    out: list[ScienceNuggetCard] = []
    for offset in range(min(count, len(pool))):
        idx = hash((user_id or "guest", factor, scenario.sfi, offset)) % len(pool)
        n = pool[idx]
        out.append(
            ScienceNuggetCard(
                id=int(n.get("n", 0)),
                text=str(n.get("text", "")),
                factor=str(n.get("factor", "")),
                source=str(n.get("source", "")),
            )
        )
    return out


def _scenario_metadata(
    store: ScenarioStore,
    scenario: ScenarioEvaluation,
    user_id: Optional[str] = None,
) -> dict:
    cell_id = _scenario_cell_id(scenario)
    return {
        "evidence_version": None,
        "evidence_primary_id": cell_id or None,
        "evidence_carousel": None,
        "habit_alerts": None,
        "science_nuggets": _pick_scenario_nuggets(store, scenario, user_id) or None,
        "clinical_gaps": None,
        "coverage_thin_cells": None,
    }


def _evaluate(
    env: EnvironmentalData,
    *,
    profile: UserProfile | None,
    guest_mode: bool,
    city: str | None,
    local_time: datetime | None,
    store: ScenarioStore | None = None,
) -> tuple[ScenarioStore, ScenarioEvaluation]:
    store = store or get_scenario_store()
    scenario = evaluate_scenario(
        store,
        env,
        city=city or env.location_name or "Unknown",
        profile=profile,
        guest_mode=guest_mode,
        local_time=local_time,
    )
    return store, scenario


def build_alert_response(
    env: EnvironmentalData,
    score: SkinScore,
    *,
    profile: UserProfile | None = None,
    guest_mode: bool = True,
    city: str | None = None,
    local_time: datetime | None = None,
    store: ScenarioStore | None = None,
) -> AlertResponse:
    store, scenario = _evaluate(
        env,
        profile=profile,
        guest_mode=guest_mode,
        city=city,
        local_time=local_time,
        store=store,
    )
    bands = bucketize_environment(env)
    season = indian_season()
    l1 = scenario.flash_alert.l1 or scenario.flash_alert.l0
    steps = build_protection_steps_from_scenario(scenario, env)
    l1, steps, guest_nudge = apply_night_gate(
        uv_index=env.uv_index,
        l1=l1,
        steps=steps,
        guest_mode=guest_mode,
    )
    whats_happening = l1 + (guest_nudge or "")
    cell_id = _scenario_cell_id(scenario)
    factor = scenario.dominant.factor
    alert_body = (
        f"UV {env.uv_index}, temp {round(env.temperature_c, 1)}C, "
        f"AQI {env.aqi}, humidity {round(env.humidity_pct)}% — "
        f"{factor} alert ({cell_id})."
    )
    science_fact, science_source = _science_from_scenario(scenario)
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
        scenario_code=cell_id,
        scenario_number=_scenario_number(cell_id),
        health_advisory=health_advisory,
        color_code=color,
        icon=icon,
        generated_at=now.isoformat(),
        data_freshness_minutes=freshness,
        weather_api_url=env.weather_api_url,
        raw_weather_payload=env.raw_weather_payload,
        profile_mode="guest" if guest_mode else resolve_mode(profile).value,
        indian_season=season,
        environment_bands={
            "uvi": bands.uvi,
            "temperature": bands.temperature,
            "humidity": bands.humidity,
            "aqi": bands.aqi,
        },
        **_scenario_metadata(store, scenario, profile.user_id if profile else None),
    )


def _cleanser_for_skin_type(skin_type_value: str) -> str:
    return {
        "oily": "Gel cleanser",
        "dry": "Cream cleanser",
        "combination": "Gentle gel cleanser",
        "normal": "Gentle cleanser",
        "sensitive": "Ultra-gentle cleanser",
    }.get(skin_type_value, "Gentle cleanser")


def build_personalized_alert_response(
    env: EnvironmentalData,
    score: SkinScore,
    profile: UserProfile,
    *,
    city: str | None = None,
    local_time: datetime | None = None,
) -> PersonalizedAlertResponse:
    generic = build_alert_response(
        env,
        score,
        profile=profile,
        guest_mode=False,
        city=city,
        local_time=local_time,
    )
    store, scenario = _evaluate(
        env,
        profile=profile,
        guest_mode=False,
        city=city,
        local_time=local_time,
    )
    base_steps = build_protection_steps_from_scenario(scenario, env)
    personalized_steps = [
        ProtectionStep(
            step_number=step.step_number,
            action=get_textured_product(step.product_category, profile.skin_type, step.action),
            reason=step.reason,
            product_category=step.product_category,
        )
        for step in base_steps
    ]
    personalized_steps = reorder_steps_by_age(personalized_steps, profile.age_bracket)
    l1 = scenario.flash_alert.l1 or scenario.flash_alert.l0
    _, personalized_steps, _ = apply_night_gate(
        uv_index=env.uv_index,
        l1=l1,
        steps=personalized_steps,
        guest_mode=False,
    )

    mode = resolve_mode(profile)
    personalized_whats_happening = l1
    personalized_headline = l1.split(".")[0].strip()
    if not personalized_headline.endswith("."):
        personalized_headline = f"{personalized_headline}."

    personalized_key_dont = (
        get_concern_key_dont(profile.primary_concern, env) or generic.key_dont
    )
    personalized_headline = apply_language_swap(personalized_headline, profile.gender)
    personalized_whats_happening = apply_language_swap(personalized_whats_happening, profile.gender)
    personalized_key_dont = apply_language_swap(personalized_key_dont, profile.gender)
    for step in personalized_steps:
        step.action = apply_language_swap(step.action, profile.gender)

    cell_id = _scenario_cell_id(scenario)
    personalized_alert_body = (
        f"UV {env.uv_index}, temp {round(env.temperature_c, 1)}C, "
        f"AQI {env.aqi}, humidity {round(env.humidity_pct)}% — "
        f"{scenario.dominant.factor} alert ({cell_id})."
    )
    personalized_compact_headline = (
        f"{generic.icon} {_build_compact_headline(score, personalized_steps[0].action)}"
    )
    science_fact, science_source = _science_from_scenario(scenario)
    age_config = get_age_priority(profile.age_bracket)
    personalized_evening_recovery = age_config["evening_template"].format(
        cleanser=_cleanser_for_skin_type(profile.skin_type.value)
    )

    return PersonalizedAlertResponse(
        location_name=generic.location_name,
        uv_index=generic.uv_index,
        temperature_c=generic.temperature_c,
        aqi=generic.aqi,
        humidity_pct=generic.humidity_pct,
        skin_score=generic.skin_score,
        compact_headline=personalized_compact_headline,
        score_badge=generic.score_badge,
        expand_cta=generic.expand_cta,
        whats_happening=personalized_whats_happening,
        alert_body=personalized_alert_body,
        protection_steps=personalized_steps,
        key_dont=personalized_key_dont,
        evening_recovery=generic.evening_recovery,
        weekly_boost=generic.weekly_boost,
        science_fact=science_fact,
        science_source=science_source,
        scenario_code=cell_id,
        scenario_number=_scenario_number(cell_id),
        health_advisory=generic.health_advisory,
        color_code=generic.color_code,
        icon=generic.icon,
        generated_at=generic.generated_at,
        data_freshness_minutes=generic.data_freshness_minutes,
        weather_api_url=generic.weather_api_url,
        raw_weather_payload=generic.raw_weather_payload,
        is_personalized=True,
        skin_type_used=profile.skin_type,
        primary_concern_used=profile.primary_concern,
        fitzpatrick_type=profile.fitzpatrick_type,
        personalized_burn_time=calculate_burn_time(env.uv_index, profile.fitzpatrick_type),
        personalized_steps=personalized_steps,
        personalized_headline=personalized_headline,
        personalized_whats_happening=personalized_whats_happening,
        personalized_key_dont=personalized_key_dont,
        gender_tip=get_gender_tip(profile.gender, env),
        hair_alert=generate_hair_alert(profile, env),
        personalized_evening_recovery=personalized_evening_recovery,
        profile_mode=mode.value,
        profile_completeness=profile_completeness(profile),
        indian_season=generic.indian_season,
        environment_bands=generic.environment_bands,
        **_scenario_metadata(store, scenario, profile.user_id),
    )
