"""Forecast day template matching + week-ahead assembly."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from app.hlhp.core.bands import EnvironmentBands, bucketize_environment
from app.hlhp.evidence.composition_store import get_composition_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.outdoor_ok import compute_outdoor_ok, pick_mood_verdict


def _match_template(
    templates: list[dict],
    *,
    bands: EnvironmentBands,
    concern_id: str | None,
    mood: str = "",
) -> Optional[dict]:
    cid = (concern_id or "").strip().lower()
    mood_key = (mood or "").strip().lower()

    def score(row: dict) -> int:
        s = 0
        for dim, band in (
            ("uv_band", bands.uvi),
            ("temp_band", bands.temperature),
            ("aqi_band", bands.aqi),
            ("rh_band", bands.humidity),
        ):
            allowed = str(row.get(dim) or "any").strip().lower()
            if allowed in ("any", ""):
                s += 1
            elif allowed == band:
                s += 3
        row_concern = str(row.get("concern_id") or "any").strip().lower()
        if row_concern in ("any", ""):
            s += 1
        elif cid and row_concern == cid:
            s += 4
        ext = str(row.get("mood_verdict_extension") or "").strip().lower()
        if ext and mood_key and ext == mood_key:
            s += 2
        return s

    if not templates:
        return None
    ranked = sorted(templates, key=score, reverse=True)
    best = ranked[0]
    if score(best) <= 0:
        return None
    return best


def forecast_oneliner(
    *,
    bands: EnvironmentBands,
    concern_id: str | None = None,
    mood: str = "",
) -> str:
    store = get_composition_store()
    templates = store.composition.get("forecast_day_templates") or []
    hit = _match_template(templates, bands=bands, concern_id=concern_id, mood=mood)
    if hit and hit.get("forecast_one_liner"):
        return str(hit["forecast_one_liner"])
    return ""


def assemble_week_ahead(
    *,
    base_env: EnvironmentalData,
    concern_id: str | None,
    mood_today: str,
    days: int = 7,
    start: datetime | None = None,
) -> list[dict[str, Any]]:
    """Simple week-ahead using today's env as baseline (forecast API upgrade later)."""
    store = get_composition_store()
    templates = store.composition.get("forecast_day_templates") or []
    when = start or base_env.fetched_at
    out: list[dict[str, Any]] = []

    for offset in range(days):
        day = when + timedelta(days=offset)
        # slight synthetic drift for demo until multi-day forecast wired
        uvi = max(0.0, base_env.uv_index - 0.3 * offset)
        temp = base_env.temperature_c + (0.5 if offset % 2 else -0.2)
        aqi = base_env.aqi
        rh = min(100.0, base_env.humidity_pct + offset * 1.5)
        env = EnvironmentalData(
            uv_index=uvi,
            temperature_c=temp,
            aqi=aqi,
            humidity_pct=rh,
            location_name=base_env.location_name,
            fetched_at=day,
            data_sources=base_env.data_sources,
        )
        bands = bucketize_environment(env)
        mood = mood_today if offset == 0 else ""
        hit = _match_template(templates, bands=bands, concern_id=concern_id, mood=mood)
        score, band_text = compute_outdoor_ok(env)
        mood_verdict = pick_mood_verdict(bands)
        oneliner = (hit or {}).get("forecast_one_liner") or forecast_oneliner(
            bands=bands, concern_id=concern_id, mood=mood
        ) or band_text
        out.append(
            {
                "date": day.date().isoformat(),
                "day_label": "Today" if offset == 0 else day.strftime("%a %d %b"),
                "outdoor_ok_score": score,
                "outdoor_ok_band_text": band_text,
                "mood_verdict": mood_verdict,
                "forecast_text": oneliner or "Steady routine carries the week.",
                "is_today": offset == 0,
            }
        )
    return out
