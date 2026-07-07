"""Assemble intraday SFI timeline for history + plan-ahead charts."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.engine_models import EnvironmentalData as EngineEnv
from app.hlhp.models.engine_models import SkinConcern as EngineConcern
from app.hlhp.models.engine_models import SkinType as EngineSkinType
from app.hlhp.models.engine_models import UserProfile as EngineProfile
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.sfi_timeline import (
    SfiScanOverlayPoint,
    SfiTimelinePoint,
    SfiTimelineResponse,
)
from app.hlhp.services.outdoor_ok import compute_outdoor_ok
from app.hlhp.services.scan_log_store import fetch_scans
from app.hlhp.services.scoring import compute_sfi
from app.hlhp.services.weatherapi_timeline import (
    HourlyEnvReading,
    fetch_timeline_hourly_readings,
    local_today,
)


def _profile_to_engine(profile: UserProfile | None) -> EngineProfile | None:
    if profile is None:
        return None
    skin_type = None
    if profile.skin_type is not None:
        try:
            skin_type = EngineSkinType(profile.skin_type.value)
        except ValueError:
            skin_type = None
    concerns: list[EngineConcern] = []
    for item in profile.skin_concerns:
        try:
            concerns.append(EngineConcern(item.value))
        except ValueError:
            continue
    if skin_type is None and not concerns:
        return None
    return EngineProfile(skin_type=skin_type, concerns=concerns)


def profile_adjusts_sfi(profile: UserProfile | None) -> bool:
    return _profile_to_engine(profile) is not None


def _sfi_scores(
    reading: HourlyEnvReading,
    *,
    location_name: str,
    profile: UserProfile | None,
) -> tuple[int, int]:
    env = EnvironmentalData(
        uv_index=reading.uv_index,
        temperature_c=reading.temp_c,
        aqi=reading.aqi,
        humidity_pct=reading.humidity_pct,
        location_name=location_name,
    )
    sfi_env, _ = compute_outdoor_ok(env)
    engine_profile = _profile_to_engine(profile)
    if engine_profile is None:
        return sfi_env, sfi_env

    engine_env = EngineEnv(
        location=location_name,
        uv_index=reading.uv_index,
        temperature_c=reading.temp_c,
        aqi=reading.aqi,
        humidity_pct=reading.humidity_pct,
    )
    sfi_personalised, *_ = compute_sfi(engine_env, engine_profile)
    return sfi_env, int(sfi_personalised)


def _day_offset(iso_date: str, *, tz_id: str) -> int:
    try:
        anchor = local_today(tz_id)
        point = date.fromisoformat(iso_date)
        return (point - anchor).days
    except ValueError:
        return 0


def _reading_to_point(
    reading: HourlyEnvReading,
    *,
    tz_id: str,
    location_name: str,
    profile: UserProfile | None,
) -> SfiTimelinePoint:
    sfi_env, sfi = _sfi_scores(reading, location_name=location_name, profile=profile)
    return SfiTimelinePoint(
        at=reading.local_time,
        at_epoch=reading.at_epoch,
        day_offset=_day_offset(reading.date, tz_id=tz_id),
        slot_hour=reading.slot_hour,
        source=reading.source,  # type: ignore[arg-type]
        temp_c=reading.temp_c,
        aqi=reading.aqi,
        uv_index=reading.uv_index,
        humidity_pct=reading.humidity_pct,
        sfi_env=sfi_env,
        sfi=sfi,
    )


async def _scan_overlays(
    user_id: str,
    *,
    tz_id: str,
    days_back: int,
    days_ahead: int,
) -> list[SfiScanOverlayPoint]:
    try:
        tz = ZoneInfo(tz_id)
    except Exception:
        tz = timezone.utc

    today = datetime.now(tz).date()
    window_start = datetime.combine(
        today - timedelta(days=days_back),
        datetime.min.time(),
        tzinfo=tz,
    ).astimezone(timezone.utc)
    window_end = datetime.combine(
        today + timedelta(days=days_ahead),
        datetime.max.time(),
        tzinfo=tz,
    ).astimezone(timezone.utc)

    scans = await fetch_scans(user_id, since=window_start, limit=500)
    overlays: list[SfiScanOverlayPoint] = []
    for scan in scans:
        scanned_at = scan.get("scanned_at")
        if not scanned_at:
            continue
        if isinstance(scanned_at, datetime):
            dt = scanned_at if scanned_at.tzinfo else scanned_at.replace(tzinfo=timezone.utc)
        else:
            continue
        if dt > window_end:
            continue
        local = dt.astimezone(tz)
        overlays.append(
            SfiScanOverlayPoint(
                at=local.strftime("%Y-%m-%d %H:%M"),
                at_epoch=int(local.timestamp()),
                sfi_observed=int(scan.get("outdoor_ok_score", 0)),
            )
        )
    overlays.sort(key=lambda o: o.at_epoch)
    return overlays


async def assemble_sfi_timeline(
    *,
    latitude: float,
    longitude: float,
    city: str,
    user_id: str | None = None,
    profile: UserProfile | None = None,
    days_back: int = 3,
    days_ahead: int = 3,
) -> SfiTimelineResponse:
    store = get_scenario_store()
    readings, tz_id, location_name = await fetch_timeline_hourly_readings(
        latitude,
        longitude,
        days_back=days_back,
        days_ahead=days_ahead,
    )
    location_label = city or location_name
    engine_profile = _profile_to_engine(profile) if user_id and profile else None
    profile_curve_active = engine_profile is not None
    signed_in = bool(user_id and profile)

    points = [
        _reading_to_point(
            r,
            tz_id=tz_id,
            location_name=location_label,
            profile=profile if engine_profile else None,
        )
        for r in readings
    ]

    scan_overlays: list[SfiScanOverlayPoint] = []
    if user_id:
        scan_overlays = await _scan_overlays(
            user_id,
            tz_id=tz_id,
            days_back=days_back,
            days_ahead=days_ahead,
        )

    source = "weatherapi" if points else "unavailable"
    return SfiTimelineResponse(
        mode="personalised" if signed_in else "guest",
        profile_curve_active=profile_curve_active,
        timezone=tz_id,
        days_back=days_back,
        days_ahead=days_ahead,
        location_name=location_label,
        points=points,
        scan_overlays=scan_overlays,
        forecast_source=source,
        workbook_version=store.workbook_version,
    )
