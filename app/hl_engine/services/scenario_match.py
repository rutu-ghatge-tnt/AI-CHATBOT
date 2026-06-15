"""Binary scenario matcher — picks one of the 16 codes."""

from app.hl_engine.data.scenarios import SCENARIOS
from app.hl_engine.data.thresholds import SCENARIO_CUTS
from app.hl_engine.models.engine_models import EnvironmentalData


def _bits(env: EnvironmentalData) -> tuple[bool, bool, bool, bool]:
    c = SCENARIO_CUTS
    return (
        env.temperature_c >= c["temp_high"],
        env.aqi > c["aqi_high"],
        env.uv_index >= c["uvi_high"],
        env.humidity_pct >= c["humidity_high"],
    )


# Maps (T, A, U, H) bits to scenario number.
_MAP = {
    (True,  True,  True,  False): 1,
    (True,  False, True,  False): 2,
    (True,  True,  True,  True):  3,
    (True,  False, True,  True):  4,
    (False, True,  True,  False): 5,
    (False, False, True,  False): 6,
    (False, True,  True,  True):  7,
    (False, False, True,  True):  8,
    (False, True,  False, False): 9,
    (False, False, False, False): 10,
    (False, True,  False, True):  11,
    (False, False, False, True):  12,
    (True,  True,  False, False): 13,
    (True,  False, False, False): 14,
    (True,  True,  False, True):  15,
    (True,  False, False, True):  16,
}


def match(env: EnvironmentalData) -> dict:
    """Return the matched scenario dict."""
    num = _MAP.get(_bits(env), 10)
    return SCENARIOS[num]
