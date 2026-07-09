"""Unit tests for HLHP V4 scoring engine (handoff §3)."""

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.v4_scoring_engine import (
    environmental_sfi,
    evaluate_v4,
    mode_for_sfi,
    personal_sfi,
    scene_key,
)


def _env(**kwargs) -> EnvironmentalData:
    defaults = dict(
        uv_index=6.0,
        temperature_c=28.0,
        aqi=80,
        humidity_pct=52.0,
        wind_kmh=10.0,
        location_name="Pune",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def test_environmental_sfi_matches_handoff_example():
    env = _env()
    eval_ = evaluate_v4(env, None, guest_mode=True)
    assert eval_.environmental_sfi == 67
    assert eval_.dominant_factor == "Temperature"
    assert eval_.mode == "Guard Up"


def test_personal_sfi_concern_weighting():
    env = _env()
    profile = UserProfile(
        user_id="test-user",
        skin_type=SkinType.DRY,
        skin_concerns=[SkinConcern.MELASMA],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    eval_ = evaluate_v4(env, profile, guest_mode=False)
    assert eval_.personal_sfi is not None
    assert eval_.headline_sfi == eval_.personal_sfi
    assert eval_.personal_sfi <= eval_.environmental_sfi


def test_scene_clear_and_windy():
    assert scene_key(_env()) == "clear"
    assert scene_key(_env(wind_kmh=35)) == "windy"
    assert scene_key(_env(), surge=True) == "storm"
    assert scene_key(_env(temperature_c=5)) == "snow"


def test_mode_ladder():
    assert mode_for_sfi(90) == "Paradise Mode"
    assert mode_for_sfi(75) == "Smooth Sailing"
    assert mode_for_sfi(60) == "Guard Up"
    assert mode_for_sfi(45) == "Battle Stations"
    assert mode_for_sfi(30) == "Hostile Mode"
    assert mode_for_sfi(10) == "Code Red"


def test_dominant_driver_tie_break():
    env = _env(temperature_c=28.0, uv_index=6.0, humidity_pct=52.0, aqi=80)
    eval_ = evaluate_v4(env, None, guest_mode=True)
    assert eval_.dominant_factor == "Temperature"
