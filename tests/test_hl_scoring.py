from datetime import datetime, timezone

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.scenario_matcher import match_scenario
from app.hlhp.services.scoring_engine import calculate_skin_score


def _make_env(**kwargs):
    defaults = dict(
        uv_index=5.0,
        temperature_c=25.0,
        aqi=50,
        humidity_pct=45.0,
        location_name="Test City",
        fetched_at=datetime.now(timezone.utc),
        data_sources={},
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def test_perfect_conditions_score():
    env = _make_env(uv_index=1, temperature_c=23, aqi=30, humidity_pct=45)
    score = calculate_skin_score(env)
    assert score.total == 100
    assert score.band.value == "Paradise Mode"


def test_worst_case_score():
    env = _make_env(uv_index=12, temperature_c=45, aqi=450, humidity_pct=5)
    score = calculate_skin_score(env)
    assert score.total == 0
    assert score.band.value == "Code Red"


def test_scenario_mapping():
    env = _make_env(uv_index=8.5, temperature_c=38, aqi=150, humidity_pct=20)
    num, code = match_scenario(env)
    assert num == 1
    assert code == "HT-HA-HU-LH"

