"""Outdoor mood verdict — derived from band states.

The legacy numeric `compute_outdoor_ok` scorer has been removed because all
production scoring now comes from the unified V4 SFI engine (`resolve_sfi`).
"""

from __future__ import annotations

from app.hlhp.core.bands import EnvironmentBands


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
