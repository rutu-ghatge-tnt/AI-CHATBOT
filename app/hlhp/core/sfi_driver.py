"""Map environmental readings to recap driver keys."""

from __future__ import annotations

from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.score import SkinScore
from app.hlhp.services.scoring_engine import calculate_skin_score

_DRIVER_MAP = {
    "uv_index": "uv",
    "temperature": "temp",
    "aqi": "aqi",
    "humidity": "humidity",
}


def driver_key_from_score(score: SkinScore) -> str:
    if score.total >= 75:
        return "comfort"
    return _DRIVER_MAP.get(score.dominant_threat, "comfort")


def driver_key_from_env(env: EnvironmentalData) -> str:
    return driver_key_from_score(calculate_skin_score(env))


def bands_snapshot(bands: EnvironmentBands) -> dict[str, str]:
    return {
        "temp_band": bands.temperature,
        "uv_band": bands.uvi,
        "aqi_band": bands.aqi,
        "humidity_band": bands.humidity,
}
