"""Outdoor-OK composite score per HLHP Engine Implementation Spec v2 §5."""

from __future__ import annotations

from app.hlhp.core.bands import EnvironmentBands, bucketize_aqi, bucketize_humidity
from app.hlhp.models.environmental import EnvironmentalData

_BAND_TEXT = (
    (80, "Easy day to be outside"),
    (60, "Comfortable with sunscreen"),
    (40, "Manageable — protect the basics"),
    (20, "Plan around it — combo stress"),
    (0, "Hard outdoor day — head-to-toe protection helps most"),
)


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y1
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)


def uv_penalty(uvi: float) -> float:
    if uvi <= 0:
        return 0.0
    if uvi >= 11:
        return 60.0
    return _lerp(uvi, 0, 11, 0, 60)


def pollution_penalty(aqi: int) -> float:
    if aqi <= 50:
        return 0.0
    if aqi >= 401:
        return 70.0
    return _lerp(float(aqi), 50, 401, 0, 70)


def temperature_penalty(temp_c: float) -> float:
    if 18 <= temp_c <= 28:
        return 0.0
    if temp_c < 18:
        if temp_c <= 10:
            return 50.0
        return _lerp(temp_c, 10, 18, 50, 0)
    if temp_c >= 38:
        return 50.0
    return _lerp(temp_c, 28, 38, 0, 50)


def humidity_penalty(rh: float) -> float:
    if 40 <= rh <= 60:
        return 0.0
    if rh < 40:
        if rh <= 25:
            return 30.0
        return _lerp(rh, 25, 40, 30, 0)
    if rh >= 75:
        return 30.0
    return _lerp(rh, 60, 75, 0, 30)


def compute_outdoor_ok(env: EnvironmentalData) -> tuple[int, str]:
    raw = (
        100.0
        - 1.5 * uv_penalty(env.uv_index)
        - 1.2 * pollution_penalty(env.aqi)
        - 1.0 * temperature_penalty(env.temperature_c)
        - 0.6 * humidity_penalty(env.humidity_pct)
    )
    score = int(_clip(raw, 0, 100))
    band_text = _BAND_TEXT[-1][1]
    for threshold, text in _BAND_TEXT:
        if score >= threshold:
            band_text = text
            break
    return score, band_text


def pick_mood_verdict(bands: EnvironmentBands, primary_tag: str = "") -> str:
    if primary_tag:
        return primary_tag
    strong = sum(
        1
        for band in (
            bands.uvi in {"high", "very_high", "extreme"},
            bands.aqi in {"poor", "very_poor", "severe"},
            bands.temperature in {"hot", "very_hot"},
            bands.humidity in {"very_low", "very_high"},
        )
        if band
    )
    if strong >= 3:
        return "stack_day"
    if bands.uvi in {"very_high", "extreme"} and bands.aqi in {"moderate", "poor", "very_poor", "severe"}:
        return "oxidative_load_day"
    if bands.uvi in {"very_high", "extreme"}:
        return "pigment_overdrive_day"
    if strong >= 2:
        return "manageable_day"
    if strong == 1:
        return "comfortable_day"
    return "easy_day"
