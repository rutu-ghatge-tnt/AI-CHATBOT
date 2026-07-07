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

COMFORT_SFI_THRESHOLD = 75


def driver_key_for_day(
    *,
    outdoor_score_avg: float | None,
    env: EnvironmentalData,
) -> str | None:
    """Recap bar colour from the day's averaged SFI + representative env readings."""
    if outdoor_score_avg is None:
        return None
    if outdoor_score_avg >= COMFORT_SFI_THRESHOLD:
        return "comfort"
    score = calculate_skin_score(env)
    return _DRIVER_MAP.get(score.dominant_threat, "comfort")


def driver_key_from_score(score: SkinScore) -> str:
    """Instantaneous driver from a single env score (Hello / live scan)."""
    if score.total >= COMFORT_SFI_THRESHOLD:
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
