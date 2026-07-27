"""Daily representative SFI scores — align history, plan-ahead, and charts."""

from __future__ import annotations

from datetime import datetime

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.sfi_timeline import SfiTimelinePoint
from app.hlhp.services.sfi_unified import outdoor_ok_from_env
from app.hlhp.services.weatherapi_forecast import ForecastDayReading

REPRESENTATIVE_SLOT_HOUR = 12


def _forecast_reading_to_env(reading: ForecastDayReading, *, location_name: str) -> EnvironmentalData:
    return EnvironmentalData(
        uv_index=reading.uv_index,
        temperature_c=reading.temp_c,
        aqi=reading.aqi,
        humidity_pct=reading.humidity_pct,
        location_name=location_name,
        fetched_at=datetime.now(),
        data_sources={"weather": "weatherapi", "aqi": "weatherapi", "uv": "open_meteo"},
    )


def lowest_daily_slot_from_points(
    points: list[SfiTimelinePoint],
    date_key: str,
    *,
    personalised: bool = False,
) -> SfiTimelinePoint | None:
    """Slot with the lowest SFI across 6am–9pm check-ins for one day."""
    day_points = [p for p in points if p.at.startswith(date_key)]
    if not day_points:
        return None
    if personalised:
        return min(day_points, key=lambda p: p.sfi)
    return min(day_points, key=lambda p: p.sfi_env)


def lowest_daily_slots_by_date(
    points: list[SfiTimelinePoint],
    dates: list[str],
    *,
    personalised: bool = False,
) -> dict[str, SfiTimelinePoint]:
    out: dict[str, SfiTimelinePoint] = {}
    for date_key in dates:
        slot = lowest_daily_slot_from_points(points, date_key, personalised=personalised)
        if slot is not None:
            out[date_key] = slot
    return out


def daily_env_score_from_points(points: list[SfiTimelinePoint], date_key: str) -> int | None:
    """Noon slot env score for a day, or average of available slots."""
    day_points = [p for p in points if p.at.startswith(date_key)]
    if not day_points:
        return None
    noon = next((p for p in day_points if p.slot_hour == REPRESENTATIVE_SLOT_HOUR), None)
    if noon is not None:
        return int(noon.sfi_env)
    return int(round(sum(p.sfi_env for p in day_points) / len(day_points)))


def daily_personal_score_from_points(points: list[SfiTimelinePoint], date_key: str) -> int | None:
    day_points = [p for p in points if p.at.startswith(date_key)]
    if not day_points:
        return None
    noon = next((p for p in day_points if p.slot_hour == REPRESENTATIVE_SLOT_HOUR), None)
    if noon is not None:
        return int(noon.sfi)
    return int(round(sum(p.sfi for p in day_points) / len(day_points)))


def average_daily_env_scores(points: list[SfiTimelinePoint]) -> dict[str, int]:
    dates = sorted({p.at[:10] for p in points})
    out: dict[str, int] = {}
    for date_key in dates:
        score = daily_env_score_from_points(points, date_key)
        if score is not None:
            out[date_key] = score
    return out


def apply_forecast_daily_env_scores(
    points: list[SfiTimelinePoint],
    readings: list[ForecastDayReading],
    *,
    location_name: str,
) -> list[SfiTimelinePoint]:
    """Align forward-day noon chart scores with plan-ahead list (daily forecast UV)."""
    if not readings:
        return points

    by_date: dict[str, ForecastDayReading] = {r.date: r for r in readings}
    patched: list[SfiTimelinePoint] = []

    for point in points:
        date_key = point.at[:10]
        reading = by_date.get(date_key)
        if reading is None or point.day_offset < 0 or point.slot_hour != REPRESENTATIVE_SLOT_HOUR:
            patched.append(point)
            continue

        env = _forecast_reading_to_env(reading, location_name=location_name)
        score, _ = outdoor_ok_from_env(env, guest_mode=True)
        patched.append(
            point.model_copy(
                update={
                    "sfi_env": score,
                    "uv_index": reading.uv_index,
                    "temp_c": reading.temp_c,
                    "aqi": reading.aqi,
                    "humidity_pct": reading.humidity_pct,
                }
            )
        )

    return patched
