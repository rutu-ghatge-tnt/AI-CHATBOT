from datetime import datetime, timezone

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    HairConcern,
    HairType,
    SkinConcern,
    SkinType,
    UserProfile,
)
from app.hlhp.services.alert_generator import generate_alert
from app.hlhp.services.profile_personalizer import personalize_alert
from app.hlhp.services.scoring_engine import calculate_skin_score


def _make_env(**kwargs):
    defaults = dict(
        uv_index=8.9,
        temperature_c=38.9,
        aqi=128,
        humidity_pct=11,
        location_name="Test City",
        fetched_at=datetime.now(timezone.utc),
        data_sources={},
        raw_weather_payload={},
        weather_api_url="https://example.org/weather",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def _make_profile(**kwargs):
    defaults = dict(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
        hair_type=None,
        hair_concerns=[],
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


def test_personalized_steps_have_texture_swap():
    env = _make_env()
    score = calculate_skin_score(env)
    generic = generate_alert(env, score)
    profile = _make_profile(skin_type=SkinType.OILY)
    result = personalize_alert(generic, profile, env, score)
    moisturizer_step = next(s for s in result.personalized_steps if s.product_category == "moisturizer")
    assert "gel" in moisturizer_step.action.lower()


def test_personalized_headline_changes_with_profile():
    env = _make_env()
    score = calculate_skin_score(env)
    generic = generate_alert(env, score)
    profile = _make_profile(skin_concerns=[SkinConcern.PIGMENTATION])
    result = personalize_alert(generic, profile, env, score)
    assert result.personalized_headline != generic.compact_headline


def test_hair_alert_generated_for_triggered_profile():
    env = _make_env(humidity_pct=12)
    score = calculate_skin_score(env)
    generic = generate_alert(env, score)
    profile = _make_profile(hair_type=HairType.CURLY, hair_concerns=[HairConcern.DRYNESS])
    result = personalize_alert(generic, profile, env, score)
    assert result.hair_alert is not None
