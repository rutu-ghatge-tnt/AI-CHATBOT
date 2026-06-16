"""
Unified HLHP engine — evidence workbook is the single source of truth.
"""

from app.hlhp.evidence.selector import select_evidence_bundle
from app.hlhp.models.engine_models import (
    Alert,
    EngineResponse,
    EnvironmentalData,
    ScienceTip,
    UserProfile,
)
from app.hlhp.services.scenario_matcher import match_scenario
from app.hlhp.services.scoring import compute_sfi


def _profile_summary(profile: UserProfile | None) -> str:
    if profile is None:
        return "guest"
    return " · ".join(
        [
            profile.skin_type.value,
            profile.primary_concern.value,
        ]
    )


def evaluate(
    env: EnvironmentalData,
    profile: UserProfile | None = None,
) -> EngineResponse:
    sfi, band_name, band_color, is_personalized, breakdown, dominant = compute_sfi(
        env, profile
    )

    guest_mode = profile is None
    bundle = select_evidence_bundle(env, profile=profile, guest_mode=guest_mode)
    if bundle.primary is None:
        raise RuntimeError("No evidence row matched for engine evaluation")

    primary = bundle.primary
    finding = primary.finding

    alert = Alert(
        l1=primary.l1_text,
        l2=finding.product_implication or finding.mechanism,
        l3=finding.science_citation,
    )
    tip = ScienceTip(fact=primary.science_fact, source=primary.science_source)

    _, scenario_code = match_scenario(env)

    return EngineResponse(
        skin_friendliness_index=sfi,
        band=band_name,
        band_color=band_color,
        is_personalized=is_personalized,
        factor_breakdown=breakdown,
        location=env.location,
        readings=env,
        scenario_code=finding.id,
        scenario_name=f"{finding.factor} · {scenario_code}",
        alert=alert,
        science_tip=tip,
        profile_summary=_profile_summary(profile),
    )
