"""Unit tests for HLHP SFI scoring engine (Latest-SFI six-stage model)."""

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.v4_scoring_engine import (
    evaluate_v4,
    mode_for_sfi,
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


def test_environmental_sfi_weighted_mean():
    env = _env()
    eval_ = evaluate_v4(env, None, guest_mode=True)
    # UV high=11, Temp warm=12, Hum optimal=25, AQI satisfactory=18
    # w={0.33,0.22,0.22,0.22} → round to 64
    assert eval_.environmental_sfi == 64
    assert eval_.dominant_factor == "UV"
    assert eval_.mode == "Guard Up"
    assert eval_.override_active is False


def test_personal_sfi_concern_and_skin_penalties():
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
    assert eval_.archetype == "photo_led"
    assert eval_.rho_concern >= 0
    assert eval_.rho_skin >= 0
    assert eval_.personal_sfi == eval_.environmental_sfi - eval_.rho_concern - eval_.rho_skin


def test_hazard_override_caps_extreme_uv():
    env = _env(uv_index=11.0, temperature_c=24.0, humidity_pct=50.0, aqi=45)
    eval_ = evaluate_v4(env, None, guest_mode=True)
    assert eval_.override_active is True
    assert eval_.environmental_sfi <= 54


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


def test_dominant_driver_lowest_points():
    env = _env(temperature_c=28.0, uv_index=6.0, humidity_pct=52.0, aqi=80)
    eval_ = evaluate_v4(env, None, guest_mode=True)
    assert eval_.dominant_factor == "UV"
