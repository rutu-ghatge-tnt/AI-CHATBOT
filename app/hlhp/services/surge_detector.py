"""Environmental state detection for HLHP Today / alerts.

Two distinct states, deliberately separated (decision Q5):

``adverse``
    Absolute readings sit in a harmful band right now. Common in Indian
    conditions -- Delhi in November, Mumbai in July, Pune in May are all
    adverse. Drives the conditions scene (haze / heat / rain) and L1 copy.

``surge``
    Conditions changed *suddenly* relative to the rolling 7-day baseline.
    Genuinely episodic. Drives the storm scene and L2 copy.

Before this split both were computed from absolute thresholds, so ``surge``
was true on roughly 7 days in 10 and forced the storm scene -- which made the
``haze`` and ``heat`` scenes unreachable and ran L2 copy almost daily.

Surge requires a stored baseline. With no history it is simply False and the
adverse layer carries the alerting, so a first-run city still behaves sensibly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.hlhp.composition.delta import compute_env_delta
from app.hlhp.models.environmental import EnvironmentalData

# Rolling 7-day delta thresholds -- true surge. Mirrors composition/delta.py.
_DELTA_RH_SURGE = 15.0
_DELTA_TEMP_SURGE = 4.0
_DELTA_UVI_SURGE = 2.0
_DELTA_AQI_SURGE = 60

# Absolute adverse-band triggers -- present-state harm, not change.
_ABS_AQI_POOR = 201
_ABS_TEMP_HOT = 35.0
_ABS_RH_HIGH = 80.0
_ABS_UVI_VERY_HIGH = 8.0


@dataclass(frozen=True)
class SurgeAssessment:
    """Combined adverse / surge assessment.

    ``active`` means a true (delta-driven) surge and is what should be passed
    to ``scene_key(..., surge=...)``. ``adverse`` means absolute conditions are
    harmful right now.
    """

    active: bool
    tags: list[str] = field(default_factory=list)
    forced: bool = False
    adverse: bool = False
    adverse_tags: list[str] = field(default_factory=list)

    @property
    def alert_level(self) -> str:
        """Copy register: L2 for a surge, L1 for adverse conditions, else L0."""
        if self.active:
            return "L2"
        if self.adverse:
            return "L1"
        return "L0"

    @property
    def all_tags(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for t in [*self.tags, *self.adverse_tags]:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out


def _dedupe(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def assess_adverse(env: EnvironmentalData) -> list[str]:
    """Absolute adverse-condition tags from the present reading alone."""
    tags: list[str] = []
    if env.aqi >= _ABS_AQI_POOR:
        tags.append("pollution_adverse")
    if env.temperature_c >= _ABS_TEMP_HOT:
        tags.append("heat_adverse")
    if env.humidity_pct >= _ABS_RH_HIGH:
        tags.append("humidity_adverse")
    if env.uv_index >= _ABS_UVI_VERY_HIGH:
        tags.append("uv_adverse")
    return tags


def assess_surge(
    env: EnvironmentalData,
    *,
    baseline: dict | None = None,
    force: bool = False,
    extra_tags: list[str] | None = None,
) -> SurgeAssessment:
    """Assess sudden change (surge) and present-state harm (adverse).

    ``force`` is the demo toggle; real surges never inflate env readings.
    """
    adverse_tags = assess_adverse(env)

    if force:
        tags = _dedupe([*(extra_tags or []), "forced_surge"])
        return SurgeAssessment(
            active=True,
            tags=tags,
            forced=True,
            adverse=bool(adverse_tags),
            adverse_tags=adverse_tags,
        )

    # True surge is delta-only and needs a baseline. Without one it is False,
    # and the adverse layer carries the alerting.
    surge_tags: list[str] = []
    if baseline:
        delta = compute_env_delta(
            env.uv_index,
            env.temperature_c,
            env.aqi,
            env.humidity_pct,
            baseline=baseline,
        )
        surge_tags = list(delta.sudden_tags)

    if extra_tags:
        surge_tags.extend(extra_tags)
    surge_tags = _dedupe(surge_tags)

    return SurgeAssessment(
        active=bool(surge_tags),
        tags=surge_tags,
        forced=False,
        adverse=bool(adverse_tags),
        adverse_tags=adverse_tags,
    )
