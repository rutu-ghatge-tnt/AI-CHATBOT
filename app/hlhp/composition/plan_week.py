"""Plan your week — real forecast → outdoor friendliness scores."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.hlhp.composition.forecast import _match_template, forecast_oneliner
from app.hlhp.composition.sfi_daily import lowest_daily_slots_by_date
from app.hlhp.composition.sfi_timeline import _profile_to_engine, _reading_to_point
from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.evidence.composition_store import get_composition_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.sfi_timeline import SfiTimelinePoint
from app.hlhp.services.outdoor_ok import pick_mood_verdict
from app.hlhp.services.sfi_unified import outdoor_band_for_score, outdoor_ok_from_env
from app.hlhp.services.weatherapi_forecast import ForecastDayReading, fetch_weatherapi_forecast
from app.hlhp.services.weatherapi_timeline import fetch_timeline_hourly_readings


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


def _slot_to_env(slot: SfiTimelinePoint, *, location_name: str) -> EnvironmentalData:
    return EnvironmentalData(
        uv_index=slot.uv_index,
        temperature_c=slot.temp_c,
        aqi=slot.aqi,
        humidity_pct=slot.humidity_pct,
        location_name=location_name,
        fetched_at=datetime.now(),
        data_sources={"weather": "weatherapi", "aqi": "weatherapi", "uv": "weatherapi"},
    )


def assemble_plan_week_days(
    readings: list[ForecastDayReading],
    *,
    city: str,
    concern_id: str | None,
    worst_slots: dict[str, SfiTimelinePoint] | None = None,
    personalised: bool = False,
) -> list[dict[str, Any]]:
    store = get_composition_store()
    templates = store.composition.get("forecast_day_templates") or []
    location = city or "your city"
    worst_slots = worst_slots or {}
    days_out: list[dict[str, Any]] = []

    for reading in readings:
        worst = worst_slots.get(reading.date)
        if worst is not None:
            env = _slot_to_env(worst, location_name=location)
            score = int(worst.sfi if personalised else worst.sfi_env)
            uv_index = worst.uv_index
            temp_c = worst.temp_c
            aqi = worst.aqi
            humidity_pct = worst.humidity_pct
        else:
            env = _reading_to_env(reading, location_name=location)
            score, band_text = outdoor_ok_from_env(env, guest_mode=True)
            uv_index = reading.uv_index
            temp_c = reading.temp_c
            aqi = reading.aqi
            humidity_pct = reading.humidity_pct

        bands = bucketize_environment(env)
        if worst is not None:
            band_text = outdoor_band_for_score(score)
        mood = pick_mood_verdict(bands)
        hit = _match_template(
            templates,
            bands=bands,
            concern_id=concern_id,
            mood=mood,
        )
        if score < 40:
            oneliner = band_text
        else:
            oneliner = (
                (hit or {}).get("forecast_one_liner")
                or forecast_oneliner(bands=bands, concern_id=concern_id, mood=mood)
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
                "uv_index": uv_index,
                "temp_c": temp_c,
                "aqi": aqi,
                "humidity_pct": humidity_pct,
                "worst_slot_hour": worst.slot_hour if worst is not None else None,
            }
        )
    return days_out


async def assemble_plan_week(
    *,
    latitude: float,
    longitude: float,
    city: str,
    concern_id: str | None = None,
    profile: UserProfile | None = None,
    days: int = 3,
) -> dict[str, Any]:
    store = get_composition_store()
    readings = await fetch_weatherapi_forecast(latitude, longitude, days=days)
    source = "weatherapi" if readings else "unavailable"

    worst_slots: dict[str, SfiTimelinePoint] = {}
    engine_profile = _profile_to_engine(profile) if profile else None
    personalised = engine_profile is not None

    if readings:
        hourly, tz_id, location_name = await fetch_timeline_hourly_readings(
            latitude,
            longitude,
            days_back=0,
            days_ahead=max(0, days - 1),
        )
        location_label = city or location_name
        reading_dates = {r.date for r in readings}
        points = [
            _reading_to_point(
                row,
                tz_id=tz_id,
                location_name=location_label,
                profile=profile if engine_profile else None,
            )
            for row in hourly
            if row.date in reading_dates
        ]
        worst_slots = lowest_daily_slots_by_date(
            points,
            [r.date for r in readings],
            personalised=personalised,
        )

    return {
        "city": city,
        "concern_id": concern_id,
        "days": assemble_plan_week_days(
            readings,
            city=city,
            concern_id=concern_id,
            worst_slots=worst_slots,
            personalised=personalised,
        ),
        "forecast_source": source,
        "workbook_version": store.workbook_version,
    }
