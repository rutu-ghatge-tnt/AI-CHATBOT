"""Sudden environmental surge detection for HLHP Today / alerts."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.hlhp.composition.delta import compute_env_delta
from app.hlhp.models.environmental import EnvironmentalData

# Rolling 7-day delta thresholds (composition/delta.py)
_DELTA_RH_SURGE = 15.0
_DELTA_TEMP_SURGE = 4.0
_DELTA_UVI_SURGE = 2.0
_DELTA_AQI_SURGE = 60

# Absolute adverse-band triggers (today vs rolling baseline not required)
_ABS_AQI_POOR = 201
_ABS_TEMP_HOT = 35.0
_ABS_RH_HIGH = 80.0
_ABS_UVI_VERY_HIGH = 8.0


@dataclass(frozen=True)
class SurgeAssessment:
    active: bool
    tags: list[str] = field(default_factory=list)
    forced: bool = False


def assess_surge(
    env: EnvironmentalData,
    *,
    baseline: dict | None = None,
    force: bool = False,
    extra_tags: list[str] | None = None,
) -> SurgeAssessment:
    """
    Detect a sudden-event surge from rolling deltas and absolute adverse readings.

    Returns ``active=True`` when the client should use storm scene + L2 alert copy.
    ``force`` is the demo toggle; real surges never inflate env readings.
    """
    if force:
        tags = list(extra_tags or [])
        if "forced_surge" not in tags:
            tags.append("forced_surge")
        return SurgeAssessment(active=True, tags=tags, forced=True)

    delta = compute_env_delta(
        env.uv_index,
        env.temperature_c,
        env.aqi,
        env.humidity_pct,
        baseline=baseline,
    )
    tags: list[str] = list(delta.sudden_tags)
    if extra_tags:
        tags.extend(extra_tags)

    if baseline:
        if delta.aqi_delta >= _DELTA_AQI_SURGE and "pollution_surge" not in tags:
            tags.append("pollution_surge")

    if env.aqi >= _ABS_AQI_POOR and "pollution_surge" not in tags:
        tags.append("pollution_surge")
    if env.temperature_c >= _ABS_TEMP_HOT and "heat_surge" not in tags:
        tags.append("heat_surge")
    if env.humidity_pct >= _ABS_RH_HIGH and "humidity_surge" not in tags:
        tags.append("humidity_surge")
    if env.uv_index >= _ABS_UVI_VERY_HIGH and "uv_surge" not in tags:
        tags.append("uv_surge")

    # De-dupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)

    active = bool(unique)
    return SurgeAssessment(active=active, tags=unique, forced=False)
