"""7-day rolling env baseline for sudden-event tags."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class EnvDelta:
    uvi_delta: float = 0.0
    temp_delta: float = 0.0
    aqi_delta: float = 0.0
    rh_delta: float = 0.0
    sudden_tags: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.sudden_tags is None:
            self.sudden_tags = []


def compute_env_delta(
    current_uvi: float,
    current_temp: float,
    current_aqi: int,
    current_rh: float,
    baseline: Optional[dict] = None,
) -> EnvDelta:
    """Compare today vs stored 7-day baseline (Mongo scan_log — optional)."""
    if not baseline:
        return EnvDelta()

    uvi_delta = current_uvi - float(baseline.get("uvi_avg", current_uvi))
    temp_delta = current_temp - float(baseline.get("temp_avg", current_temp))
    aqi_delta = current_aqi - int(baseline.get("aqi_avg", current_aqi))
    rh_delta = current_rh - float(baseline.get("rh_avg", current_rh))

    tags: list[str] = []
    if rh_delta >= 15:
        tags.append("humidity_surge")
    if temp_delta >= 4:
        tags.append("heat_surge")
    if uvi_delta >= 2:
        tags.append("uv_surge")
    if aqi_delta >= 60:
        tags.append("pollution_surge")

    return EnvDelta(
        uvi_delta=uvi_delta,
        temp_delta=temp_delta,
        aqi_delta=aqi_delta,
        rh_delta=rh_delta,
        sudden_tags=tags,
    )


def match_sudden_breakout_alerts(
    *,
    city: str,
    month: int,
    delta: EnvDelta,
    composition: dict,
) -> list[dict]:
    """Return sudden-event alert rows whose trigger families match current signals."""
    rows = composition.get("sudden_breakout_alerts") or []
    hits: list[dict] = []
    month_names = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }
    month_label = month_names.get(month, "")

    for row in rows[:36]:
        window = str(row.get("month_window") or "")
        if month_label and month_label not in window and "any" not in window.lower():
            continue
        scope = str(row.get("city_scope") or "")
        if scope and "pan-india" not in scope.lower():
            if city.lower() not in scope.lower() and not any(
                c.strip().lower() in city.lower() for c in scope.split(",")
            ):
                continue
        ext = str(row.get("mood_verdict_extension") or "")
        if ext == "transition_shock_day" and delta.rh_delta >= 10:
            hits.append(row)
        elif "surge" in ext and delta.sudden_tags:
            hits.append(row)
    return hits[:3]
