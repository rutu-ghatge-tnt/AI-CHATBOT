"""Explore lane nugget selection tests."""

from datetime import datetime

from app.hlhp.composition.explore import _pick_daily_nugget, assemble_explore
from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile


def _profile(**kwargs) -> UserProfile:
    base = dict(
        user_id="u1",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    base.update(kwargs)
    return UserProfile(**base)


def test_pick_daily_nugget_stable_per_day():
    rows = [
        {"nugget_text": "A", "nugget_category": "mechanism", "concern_audience": "acne", "priority": 1},
        {"nugget_text": "B", "nugget_category": "skin_science", "concern_audience": "acne", "priority": 1},
        {"nugget_text": "C", "nugget_category": "mythbust", "concern_audience": "melasma", "priority": 1},
    ]
    when = datetime(2026, 6, 18, 12, 0, 0)
    profile = _profile()
    first = _pick_daily_nugget(rows, city="Mumbai", concern_id="acne", profile=profile, user_id="u1", when=when)
    again = _pick_daily_nugget(rows, city="Mumbai", concern_id="acne", profile=profile, user_id="u1", when=when)
    assert first is not None
    assert first["nugget_text"] == again["nugget_text"]
    assert first["nugget_text"] in {"A", "B"}


def test_pregnancy_nugget_excluded_without_life_stage():
    rows = [
        {
            "nugget_text": "Pregnancy-trimester acne hits 0.1-10 percent of women.",
            "concern_audience": "acne",
            "priority": 1,
        },
        {
            "nugget_text": "Over-cleansing strips the protective lipid layer.",
            "concern_audience": "acne",
            "priority": 1,
        },
    ]
    when = datetime(2026, 6, 18)
    picked = _pick_daily_nugget(
        rows,
        city="Mumbai",
        concern_id="acne",
        profile=_profile(),
        user_id="u1",
        when=when,
    )
    assert picked is not None
    assert "Pregnancy" not in picked["nugget_text"]


def test_assemble_explore_uses_profile_concern():
    payload = assemble_explore(
        "Mumbai",
        "melasma",
        user_id="u1",
        profile=_profile(skin_concerns=[SkinConcern.ACNE]),
        when=datetime(2026, 6, 18),
    )
    nugget = payload.get("science_nugget")
    assert nugget is not None
    assert nugget["text"]
    assert "category_display" in nugget
    assert "rotation_note" not in nugget
    assert "index" not in nugget


def test_assemble_explore_dullness_profile_not_acne():
    payload = assemble_explore(
        "Mumbai",
        user_id="u1",
        profile=_profile(skin_concerns=[SkinConcern.DULLNESS, SkinConcern.DEHYDRATION, SkinConcern.PORES]),
        when=datetime(2026, 6, 18),
    )
    assert payload["concern_id"] == "dullness"


def test_pick_daily_nugget_dullness_skips_acne_only():
    rows = [
        {
            "nugget_text": "Premenstrual sebum surge is real. 60-70 percent of menstruating women report breakouts.",
            "concern_audience": "acne",
            "priority": 1,
            "nugget_id": "nug_acne",
        },
        {
            "nugget_text": "Iron oxide in tinted mineral sunscreens blocks 400-450 nm visible light.",
            "concern_audience": "melasma, pigmentation_pih",
            "priority": 1,
            "nugget_id": "nug_pigment",
        },
    ]
    when = datetime(2026, 6, 18)
    profile = _profile(skin_concerns=[SkinConcern.DULLNESS])
    picked = _pick_daily_nugget(
        rows,
        city="Mumbai",
        concern_id="dullness",
        profile=profile,
        user_id="u1",
        when=when,
    )
    assert picked is not None
    assert picked["nugget_id"] == "nug_pigment"


def test_pick_daily_nugget_prefers_uv_match_when_bands_high():
    rows = [
        {
            "nugget_text": "Premenstrual sebum surge is real.",
            "concern_audience": "acne",
            "priority": 1,
            "nugget_id": "nug_acne",
        },
        {
            "nugget_text": "UVA oxidises facial oil into pore-clogging by-products after sunny days.",
            "concern_audience": "acne",
            "priority": 1,
            "nugget_id": "nug_uv",
        },
    ]
    when = datetime(2026, 6, 18)
    bands = EnvironmentBands(uvi="very_high", temperature="hot", humidity="low", aqi="moderate")
    picked = _pick_daily_nugget(
        rows,
        city="Mumbai",
        concern_id="acne",
        profile=_profile(),
        user_id="u1",
        when=when,
        bands=bands,
    )
    assert picked is not None
    assert picked["nugget_id"] == "nug_uv"


def test_mumbai_monsoon_nugget_not_shown_for_pune_user():
    rows = [
        {
            "nugget_id": "nug_140",
            "nugget_text": "Mumbai monsoon humidity reaches 90 percent for weeks at a time. Heat plus humidity drives fungal acne.",
            "concern_audience": "universal",
            "priority": 1,
        },
        {
            "nugget_id": "nug_pan",
            "nugget_text": "Oily skin still needs moisturizer. Without it, the skin compensates by producing even more oil.",
            "concern_audience": "universal",
            "priority": 1,
        },
    ]
    when = datetime(2026, 6, 23)
    profile = _profile(skin_concerns=[SkinConcern.DULLNESS])
    picked = _pick_daily_nugget(
        rows,
        city="Baner, Pune, Maharashtra",
        concern_id="dullness",
        profile=profile,
        user_id="u1",
        when=when,
        bands=EnvironmentBands(uvi="moderate", temperature="warm", humidity="very_high", aqi="moderate"),
    )
    assert picked is not None
    assert picked["nugget_id"] == "nug_pan"


def test_mumbai_monsoon_nugget_shown_for_mumbai_user():
    rows = [
        {
            "nugget_id": "nug_140",
            "nugget_text": "Mumbai monsoon humidity reaches 90 percent for weeks at a time. Heat plus humidity drives fungal acne.",
            "concern_audience": "universal",
            "priority": 1,
        },
        {
            "nugget_id": "nug_pan",
            "nugget_text": "Oily skin still needs moisturizer.",
            "concern_audience": "universal",
            "priority": 1,
        },
    ]
    when = datetime(2026, 6, 23)
    picked = _pick_daily_nugget(
        rows,
        city="Vikhroli West, Mumbai",
        concern_id="dullness",
        profile=_profile(skin_concerns=[SkinConcern.DULLNESS]),
        user_id="u1",
        when=when,
        bands=EnvironmentBands(uvi="moderate", temperature="warm", humidity="very_high", aqi="moderate"),
    )
    assert picked is not None
    assert picked["nugget_id"] == "nug_140"


def test_north_india_nugget_not_shown_for_pune_user():
    rows = [
        {
            "nugget_id": "nug_016",
            "nugget_text": (
                "North India winters routinely drop indoor humidity below 25%. "
                "Heated indoor air pulls water from skin faster than it can be replaced."
            ),
            "concern_audience": "dryness",
            "priority": 1,
        },
        {
            "nugget_id": "nug_pan",
            "nugget_text": "Oily skin still needs moisturizer. Without it, the skin compensates by producing even more oil.",
            "concern_audience": "universal",
            "priority": 1,
        },
    ]
    when = datetime(2026, 1, 15)
    picked = _pick_daily_nugget(
        rows,
        city="Baner, Pune, Maharashtra",
        concern_id="dryness",
        profile=_profile(skin_concerns=[SkinConcern.DEHYDRATION]),
        user_id="u1",
        when=when,
    )
    assert picked is not None
    assert picked["nugget_id"] == "nug_pan"


def test_north_india_nugget_matches_delhi_not_pune():
    from app.hlhp.composition.explore import _nugget_matches_city

    row = {
        "nugget_id": "nug_016",
        "nugget_text": (
            "North India winters routinely drop indoor humidity below 25%. "
            "Heated indoor air pulls water from skin faster than it can be replaced."
        ),
        "concern_audience": "dryness",
        "priority": 1,
    }
    assert _nugget_matches_city(row, "Gurgaon, NCR") is True
    assert _nugget_matches_city(row, "Baner, Pune, Maharashtra") is False
