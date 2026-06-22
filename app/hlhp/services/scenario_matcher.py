from app.hlhp.data.thresholds import SCENARIO_THRESHOLDS
from app.hlhp.models.environmental import EnvironmentalData


def _classify_binary(env: EnvironmentalData) -> dict[str, bool]:
    t = SCENARIO_THRESHOLDS
    return {
        "temp_high": env.temperature_c >= t["temp_high"],
        "aqi_high": env.aqi > t["aqi_high"],
        "uvi_high": env.uv_index >= t["uvi_high"],
        "humidity_high": env.humidity_pct >= t["humidity_high"],
    }


_SCENARIO_MAP = {
    (True, True, True, False): 1,
    (True, False, True, False): 2,
    (True, True, True, True): 3,
    (True, False, True, True): 4,
    (False, True, True, False): 5,
    (False, False, True, False): 6,
    (False, True, True, True): 7,
    (False, False, True, True): 8,
    (False, True, False, False): 9,
    (False, False, False, False): 10,
    (False, True, False, True): 11,
    (False, False, False, True): 12,
    (True, True, False, False): 13,
    (True, False, False, False): 14,
    (True, True, False, True): 15,
    (True, False, False, True): 16,
}

_SCENARIO_CODES = {
    1: "HT-HA-HU-LH",
    2: "HT-LA-HU-LH",
    3: "HT-HA-HU-HH",
    4: "HT-LA-HU-HH",
    5: "LT-HA-HU-LH",
    6: "LT-LA-HU-LH",
    7: "LT-HA-HU-HH",
    8: "LT-LA-HU-HH",
    9: "LT-HA-LU-LH",
    10: "LT-LA-LU-LH",
    11: "LT-HA-LU-HH",
    12: "LT-LA-LU-HH",
    13: "HT-HA-LU-LH",
    14: "HT-LA-LU-LH",
    15: "HT-HA-LU-HH",
    16: "HT-LA-LU-HH",
}


def match_scenario(env: EnvironmentalData) -> tuple[int, str]:
    binary = _classify_binary(env)
    key = (binary["temp_high"], binary["aqi_high"], binary["uvi_high"], binary["humidity_high"])
    scenario_num = _SCENARIO_MAP.get(key, 10)
    return scenario_num, _SCENARIO_CODES[scenario_num]

