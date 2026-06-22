from app.hlhp.core.night_gate import apply_night_gate
from app.hlhp.core.profile_mode import profile_completeness, resolve_mode
from app.hlhp.data.age_priorities import get_age_priority, reorder_steps_by_age
from app.hlhp.data.concern_emphasis import get_concern_key_dont
from app.hlhp.data.gender_language import apply_language_swap, get_gender_tip
from app.hlhp.data.texture_map import get_textured_product
from app.hlhp.evidence.response import evidence_cards
from app.hlhp.evidence.selector import select_evidence_bundle
from app.hlhp.evidence.steps import build_protection_steps
from app.hlhp.models.alert import AlertResponse, ProtectionStep
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.personalized_alert import PersonalizedAlertResponse
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.score import SkinScore
from app.hlhp.services.hair_alert_generator import generate_hair_alert
from app.hlhp.services.scoring_engine import calculate_burn_time


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


def _science_from_finding(finding) -> tuple[str, str]:
    """Keep science tip aligned with the selected evidence row."""
    if finding.quantified:
        return finding.quantified, finding.science_citation
    if finding.mechanism:
        return finding.mechanism, finding.science_citation
    return finding.alert_short or finding.sub_effect, finding.science_citation


def _cleanser_for_skin_type(skin_type_value: str) -> str:
    return {
        "oily": "Gel cleanser",
        "dry": "Cream cleanser",
        "combination": "Gentle gel cleanser",
        "normal": "Gentle cleanser",
        "sensitive": "Ultra-gentle cleanser",
    }.get(skin_type_value, "Gentle cleanser")


def personalize_alert(
    generic_alert: AlertResponse,
    profile: UserProfile,
    env: EnvironmentalData,
    score: SkinScore,
) -> PersonalizedAlertResponse:
    bundle = select_evidence_bundle(
        env, profile=profile, guest_mode=False, user_id=profile.user_id
    )
    primary = bundle.primary
    if primary is None:
        raise RuntimeError("HLHP evidence store returned no personalised match for profile")

    base_steps = build_protection_steps(primary.finding, env)
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
    _, personalized_steps, _ = apply_night_gate(
        uv_index=env.uv_index,
        l1="",
        steps=personalized_steps,
        guest_mode=False,
    )

    mode = resolve_mode(profile)
    personalized_whats_happening = primary.l1_text
    personalized_headline = primary.l1_text.split(".")[0].strip()
    if not personalized_headline.endswith("."):
        personalized_headline = f"{personalized_headline}."

    personalized_key_dont = (
        get_concern_key_dont(profile.primary_concern, env) or generic_alert.key_dont
    )

    personalized_headline = apply_language_swap(personalized_headline, profile.gender)
    personalized_whats_happening = apply_language_swap(personalized_whats_happening, profile.gender)
    personalized_key_dont = apply_language_swap(personalized_key_dont, profile.gender)
    for step in personalized_steps:
        step.action = apply_language_swap(step.action, profile.gender)

    personalized_alert_body = (
        f"UV {env.uv_index}, temp {round(env.temperature_c, 1)}C, "
        f"AQI {env.aqi}, humidity {round(env.humidity_pct)}% — "
        f"{primary.finding.factor} alert ({primary.finding.id})."
    )
    personalized_compact_headline = (
        f"{generic_alert.icon} {_build_compact_headline(score, personalized_steps[0].action)}"
    )
    personalized_science_fact, personalized_science_source = _science_from_finding(primary.finding)

    age_config = get_age_priority(profile.age_bracket)
    personalized_evening_recovery = age_config["evening_template"].format(
        cleanser=_cleanser_for_skin_type(profile.skin_type.value)
    )

    return PersonalizedAlertResponse(
        location_name=generic_alert.location_name,
        uv_index=generic_alert.uv_index,
        temperature_c=generic_alert.temperature_c,
        aqi=generic_alert.aqi,
        humidity_pct=generic_alert.humidity_pct,
        skin_score=generic_alert.skin_score,
        compact_headline=personalized_compact_headline,
        score_badge=generic_alert.score_badge,
        expand_cta=generic_alert.expand_cta,
        whats_happening=personalized_whats_happening,
        alert_body=personalized_alert_body,
        protection_steps=personalized_steps,
        key_dont=personalized_key_dont,
        evening_recovery=generic_alert.evening_recovery,
        weekly_boost=generic_alert.weekly_boost,
        science_fact=personalized_science_fact,
        science_source=personalized_science_source,
        scenario_code=primary.finding.id,
        scenario_number=primary.finding.row_number,
        health_advisory=generic_alert.health_advisory,
        color_code=generic_alert.color_code,
        icon=generic_alert.icon,
        generated_at=generic_alert.generated_at,
        data_freshness_minutes=generic_alert.data_freshness_minutes,
        weather_api_url=generic_alert.weather_api_url,
        raw_weather_payload=generic_alert.raw_weather_payload,
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
        indian_season=generic_alert.indian_season,
        environment_bands=generic_alert.environment_bands,
        **evidence_cards(bundle),
    )
