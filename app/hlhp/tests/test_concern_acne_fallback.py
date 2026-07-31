"""Non-acne profiles must never inherit acne-prone strip tips via fallback."""

from __future__ import annotations

from app.hlhp.composition.alert_copy import compose_scenario_strip_headline
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.profile_taxonomy_mapper import map_skin_concerns
from app.hlhp.services.scenario_engine import evaluate_scenario, resolve_library_concerns


def test_uneven_skin_tone_maps_to_dullness_not_post_acne():
    mapped = map_skin_concerns(["Uneven Skin Tone", "Dark Circles", "Dryness"])
    assert mapped[0] == SkinConcern.DULLNESS
    assert SkinConcern.ACNE not in mapped


def test_rutu_like_profile_does_not_get_acne_prone_tip():
    """Combination + uneven tone / dark circles / dryness at extreme humidity."""
    store = get_scenario_store()
    env = EnvironmentalData(
        temperature_c=21.7,
        uv_index=2.2,
        aqi=42,
        humidity_pct=91.0,
        location_name="Baner, Pune",
    )
    concerns = map_skin_concerns(["Uneven Skin Tone", "Dark Circles", "Dryness"])
    profile = UserProfile(
        user_id="rutu",
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_18_24,
        skin_type=SkinType.COMBINATION,
        skin_concerns=concerns,
    )
    assert "Acne" not in resolve_library_concerns(profile, False)

    scenario = evaluate_scenario(
        store, env, city="Pune", profile=profile, guest_mode=False
    )
    cell_id = str((scenario.cell or {}).get("id") or "")
    l0 = scenario.flash_alert.l0 or ""
    strip = compose_scenario_strip_headline(
        l0=scenario.flash_alert.l0,
        l1=scenario.flash_alert.l1,
        guest_mode=False,
    )

    assert "ACNE" not in cell_id.upper()
    assert "acne-prone" not in l0.lower()
    assert "acne-prone" not in strip.lower()
    # Prefer tone or dryness guidance for this profile.
    assert any(
        token in strip.lower()
        for token in ("tan", "tone", "sun protection", "moisturis", "dry")
    )


def test_missing_first_concern_tries_next_not_acne():
    """Dark circles often has no humidity cell — must fall through to dryness/tone."""
    store = get_scenario_store()
    env = EnvironmentalData(
        temperature_c=21.7,
        uv_index=2.2,
        aqi=42,
        humidity_pct=91.0,
        location_name="Pune",
    )
    profile = UserProfile(
        user_id="rutu",
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_18_24,
        skin_type=SkinType.COMBINATION,
        skin_concerns=[
            SkinConcern.DARK_CIRCLES,
            SkinConcern.DEHYDRATION,
            SkinConcern.DULLNESS,
        ],
    )
    scenario = evaluate_scenario(
        store, env, city="Pune", profile=profile, guest_mode=False
    )
    cell_id = str((scenario.cell or {}).get("id") or "")
    strip = compose_scenario_strip_headline(
        l0=scenario.flash_alert.l0,
        l1=scenario.flash_alert.l1,
        guest_mode=False,
    )
    assert "ACNE" not in cell_id.upper()
    assert "acne-prone" not in strip.lower()
    assert scenario.concern in {"Dryness", "Uneven Skin Tone / Tan"}
