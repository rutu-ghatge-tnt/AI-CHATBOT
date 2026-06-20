"""Extract background / animal assets from Skintruth location-weather payload."""

from __future__ import annotations

from typing import Any, Optional


def extract_weather_visuals(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return FE-friendly visuals from Skintruth `location-weather` JSON."""
    if not raw:
        return {
            "weather_type": None,
            "skin_care_tip": None,
            "screen_variants": [],
        }

    payload = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    if not isinstance(payload, dict):
        payload = {}

    weather = payload.get("weather") if isinstance(payload.get("weather"), dict) else {}
    current = weather.get("current") if isinstance(weather.get("current"), dict) else {}
    variants = current.get("screenVariants") if isinstance(current.get("screenVariants"), list) else []

    screen_variants: list[dict[str, Any]] = []
    weather_type: Optional[str] = None
    for row in variants:
        if not isinstance(row, dict):
            continue
        wt = row.get("weatherType")
        if wt and not weather_type:
            weather_type = str(wt)
        screen_variants.append(
            {
                "screen": row.get("screen"),
                "weather_type": wt,
                "background_image": row.get("backgroundImage"),
                "animal_image": row.get("animal"),
            }
        )

    return {
        "weather_type": weather_type,
        "skin_care_tip": weather.get("skinCareTip"),
        "screen_variants": screen_variants,
    }
