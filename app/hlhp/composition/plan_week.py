"""Plan your week — real forecast → outdoor friendliness scores."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.hlhp.composition.forecast import _match_template, forecast_oneliner
from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.outdoor_ok import compute_outdoor_ok, pick_mood_verdict
from app.hlhp.services.weatherapi_forecast import ForecastDayReading, fetch_weatherapi_forecast


def _day_label(reading: ForecastDayReading) -> str:
    if reading.is_today:
        return "Today"
    try:
        parsed = datetime.strptime(reading.date, "%Y-%m-%d")
        return parsed.strftime("%a %d %b")
    except ValueError:
        return reading.date


def _reading_to_env(
    reading: ForecastDayReading,
    *,
    location_name: str,
) -> EnvironmentalData:
    return EnvironmentalData(
        uv_index=reading.uv_index,
        temperature_c=reading.temp_c,
        aqi=reading.aqi,
        humidity_pct=reading.humidity_pct,
        location_name=location_name,
        fetched_at=datetime.now(),
        data_sources={"weather": "weatherapi", "aqi": "weatherapi", "uv": "weatherapi"},
    )


def assemble_plan_week_days(
    readings: list[ForecastDayReading],
    *,
    city: str,
    concern_id: str | None,
) -> list[dict[str, Any]]:
    store = get_evidence_store()
    templates = store.composition.get("forecast_day_templates") or []
    location = city or "your city"
    days_out: list[dict[str, Any]] = []

    for reading in readings:
        env = _reading_to_env(reading, location_name=location)
        bands = bucketize_environment(env)
        score, band_text = compute_outdoor_ok(env)
        mood = pick_mood_verdict(bands)
        hit = _match_template(
            templates,
            bands=bands,
            concern_id=concern_id,
            mood=mood if reading.is_today else "",
        )
        oneliner = (
            (hit or {}).get("forecast_one_liner")
            or forecast_oneliner(bands=bands, concern_id=concern_id, mood=mood if reading.is_today else "")
            or band_text
            or reading.condition_text
        )
        days_out.append(
            {
                "date": reading.date,
                "day_label": _day_label(reading),
                "outdoor_ok_score": score,
                "outdoor_ok_band_text": band_text,
                "mood_verdict": mood,
                "mood_display": mood_headline(mood),
                "forecast_text": str(oneliner),
                "is_today": reading.is_today,
                "uv_index": reading.uv_index,
                "temp_c": reading.temp_c,
                "aqi": reading.aqi,
                "humidity_pct": reading.humidity_pct,
            }
        )
    return days_out


async def assemble_plan_week(
    *,
    latitude: float,
    longitude: float,
    city: str,
    concern_id: str | None = None,
    days: int = 3,
) -> dict[str, Any]:
    store = get_evidence_store()
    readings = await fetch_weatherapi_forecast(latitude, longitude, days=days)
    source = "weatherapi" if readings else "unavailable"
    return {
        "city": city,
        "concern_id": concern_id,
        "days": assemble_plan_week_days(readings, city=city, concern_id=concern_id),
        "forecast_source": source,
        "workbook_version": store.workbook_version,
    }
