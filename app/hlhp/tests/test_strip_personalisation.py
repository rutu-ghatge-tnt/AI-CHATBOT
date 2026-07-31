"""Strip headlines must diverge by skin type / concern — not only shared weather openers."""

from __future__ import annotations

from app.hlhp.composition.alert_copy import compose_scenario_strip_headline
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.scenario_engine import evaluate_scenario


def test_compose_personalised_leads_with_concern_tip():
    line = compose_scenario_strip_headline(
        l0="Very humid air — sweat and oil sit on the skin. Protect acne-prone pores from breakouts now.",
        l1="Longer detail about oily skin with acne.",
        guest_mode=False,
    )
    assert line.lower().startswith("protect acne-prone")
    assert "humid" in line.lower()


def test_compose_guest_surfaces_skin_clause_from_l1():
    line = compose_scenario_strip_headline(
        l0="Very humid air — sweat and oil sit on the skin. Keep skin and folds dry; cleanse off sweat and oil.",
        l1=(
            "Very humid air — sweat and oil mix on surface. "
            "Your oily skin may respond differently here. "
            "Switch to light, non-greasy products."
        ),
        guest_mode=True,
    )
    assert "oily skin" in line.lower()
    assert line.lower() != (
        "very humid air — sweat and oil sit on the skin. "
        "keep skin and folds dry; cleanse off sweat and oil."
    ).lower()


def test_personalised_profiles_get_distinct_strip_lines():
    store = get_scenario_store()
    env = EnvironmentalData(
        temperature_c=27.1,
        uv_index=0.3,
        aqi=52,
        humidity_pct=87.0,
        location_name="Mumbai",
    )
    cases = [
        (SkinType.DRY, SkinConcern.DEHYDRATION, ("moisturis", "dry")),
        (SkinType.OILY, SkinConcern.ACNE, ("acne", "pore", "oily")),
        (SkinType.SENSITIVE, SkinConcern.SENSITIVITY, ("soothe", "eczema", "sensitive")),
        (SkinType.NORMAL, SkinConcern.DULLNESS, ("sun protection", "tone", "uneven")),
    ]
    lines: list[str] = []
    for skin, concern, needles in cases:
        profile = UserProfile(
            user_id="u1",
            gender=Gender.FEMALE,
            age_bracket=AgeBracket.AGE_25_30,
            skin_type=skin,
            skin_concerns=[concern],
        )
        scenario = evaluate_scenario(
            store, env, city="Mumbai", profile=profile, guest_mode=False
        )
        line = compose_scenario_strip_headline(
            l0=scenario.flash_alert.l0,
            l1=scenario.flash_alert.l1,
            guest_mode=False,
        )
        lines.append(line.lower())
        assert any(n in line.lower() for n in needles), (skin, concern, line)

    # At least some profiles must diverge (not all identical).
    assert len(set(lines)) >= 3


def test_guest_skins_get_distinct_strip_lines():
    store = get_scenario_store()
    env = EnvironmentalData(
        temperature_c=27.1,
        uv_index=0.3,
        aqi=52,
        humidity_pct=87.0,
        location_name="Mumbai",
    )
    lines: dict[str, str] = {}
    for skin in (SkinType.DRY, SkinType.OILY, SkinType.SENSITIVE):
        profile = UserProfile(
            user_id="u1",
            gender=Gender.FEMALE,
            age_bracket=AgeBracket.AGE_25_30,
            skin_type=skin,
            skin_concerns=[SkinConcern.ACNE],
        )
        scenario = evaluate_scenario(
            store, env, city="Mumbai", profile=profile, guest_mode=True
        )
        line = compose_scenario_strip_headline(
            l0=scenario.flash_alert.l0,
            l1=scenario.flash_alert.l1,
            guest_mode=True,
        )
        lines[skin.value] = line.lower()

    assert "dry skin" in lines["dry"]
    assert "oily skin" in lines["oily"]
    assert "sensitive skin" in lines["sensitive"]
    assert len(set(lines.values())) == 3
