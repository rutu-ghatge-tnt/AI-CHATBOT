"""Legacy env-bitmask label — kept for scoring tests and band diagnostics only."""

from app.hlhp.data.thresholds import SCENARIO_CUTS
from app.hlhp.models.engine_models import EnvironmentalData
from app.hlhp.services.scenario_matcher import match_scenario as _api_match


def _bits(env: EnvironmentalData) -> tuple[bool, bool, bool, bool]:
    c = SCENARIO_CUTS
    return (
        env.temperature_c >= c["temp_high"],
        env.aqi > c["aqi_high"],
        env.uv_index >= c["uvi_high"],
        env.humidity_pct >= c["humidity_high"],
    )


def match(env: EnvironmentalData) -> dict:
    """Return env bitmask scenario metadata (not alert content)."""
    num, code = _api_match(env)
    return {
        "number": num,
        "code": code,
        "bits": _bits(env),
    }
