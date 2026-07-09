"""
Unified HLHP engine — scenario library v3.5 is the single source of truth.
"""

from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.engine_models import (
    Alert,
    EngineResponse,
    EnvironmentalData,
    ScienceTip,
    UserProfile,
)
from app.hlhp.services.scenario_engine import evaluate_scenario
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


def _scenario_cell_id(scenario) -> str:
    if scenario.evidence_cell:
        return scenario.evidence_cell.id
    cell = scenario.cell or {}
    return str(cell.get("id", ""))


def evaluate(
    env: EnvironmentalData,
    profile: UserProfile | None = None,
) -> EngineResponse:
    sfi, band_name, band_color, is_personalized, breakdown, dominant = compute_sfi(
        env, profile
    )

    guest_mode = profile is None
    store = get_scenario_store()
    scenario = evaluate_scenario(
        store,
        env,
        city=env.location or "Unknown",
        profile=profile,
        guest_mode=guest_mode,
    )
    cell_id = _scenario_cell_id(scenario)
    l1 = scenario.flash_alert.l1 or scenario.flash_alert.l0
    l2 = scenario.flash_alert.tip or l1
    l3 = ""
    if scenario.evidence_cell:
        l3 = "|".join(scenario.evidence_cell.pmids) or scenario.evidence_cell.evidence
    if not l3:
        l3 = "SkinBB HLHP Scenario Library v3.5"

    alert = Alert(l1=l1, l2=l2, l3=l3)
    science_fact = scenario.evidence_cell.evidence if scenario.evidence_cell else l1
    tip = ScienceTip(fact=science_fact, source=l3)

    return EngineResponse(
        skin_friendliness_index=sfi,
        band=band_name,
        band_color=band_color,
        is_personalized=is_personalized,
        factor_breakdown=breakdown,
        location=env.location,
        readings=env,
        scenario_code=cell_id,
        scenario_name=f"{scenario.dominant.factor} · {cell_id}",
        alert=alert,
        science_tip=tip,
        profile_summary=_profile_summary(profile),
    )
