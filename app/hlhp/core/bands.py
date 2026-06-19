"""Formal trigger bands per HLHP Engine Implementation Spec v2 §3."""

from dataclasses import dataclass

from app.hlhp.core.trigger_bands import normalize_rh_band
from app.hlhp.models.environmental import EnvironmentalData


@dataclass(frozen=True)
class EnvironmentBands:
    uvi: str
    temperature: str
    humidity: str
    aqi: str


def bucketize_uvi(uvi: float) -> str:
    if uvi < 1:
        return "off"
    if uvi < 3:
        return "low"
    if uvi < 6:
        return "moderate"
    if uvi < 8:
        return "high"
    if uvi < 11:
        return "very_high"
    return "extreme"


def bucketize_temperature(temp_c: float) -> str:
    if temp_c < 10:
        return "very_cold"
    if temp_c < 18:
        return "cold"
    if temp_c < 28:
        return "comfortable"
    if temp_c < 32:
        return "warm"
    if temp_c < 38:
        return "hot"
    return "very_hot"


def bucketize_humidity(rh: float) -> str:
    if rh < 25:
        return "very_low"
    if rh < 40:
        return "low"
    if rh <= 60:
        return "comfortable"
    if rh <= 75:
        return "high"
    return "very_high"


def bucketize_aqi(aqi: int) -> str:
    if aqi <= 50:
        return "good"
    if aqi <= 100:
        return "satisfactory"
    if aqi <= 200:
        return "moderate"
    if aqi <= 300:
        return "poor"
    if aqi <= 400:
        return "very_poor"
    return "severe"


def bucketize_environment(env: EnvironmentalData) -> EnvironmentBands:
    return EnvironmentBands(
        uvi=bucketize_uvi(env.uv_index),
        temperature=bucketize_temperature(env.temperature_c),
        humidity=normalize_rh_band(bucketize_humidity(env.humidity_pct)),
        aqi=bucketize_aqi(env.aqi),
    )


def science_condition_tags(bands: EnvironmentBands) -> list[str]:
    """Map formal bands to science-tip tag vocabulary."""
    tags: list[str] = []
    if bands.uvi in {"high", "very_high", "extreme"}:
        tags.append("uv_high")
    if bands.temperature in {"warm", "hot", "very_hot"}:
        tags.append("temp_high")
    if bands.aqi in {"moderate", "poor", "very_poor", "severe"}:
        tags.append("aqi_high")
    rh = bands.humidity
    if rh in {"very_low", "low"}:
        tags.append("humidity_low")
    elif rh in {"high", "very_high"}:
        tags.append("humidity_high")
    return tags
