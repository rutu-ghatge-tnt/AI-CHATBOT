"""Warn-me forecast checks — runs on user activity (log / patterns fetch), not cron."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.local_date import today_local
from app.hlhp.core.sfi_driver import bands_snapshot
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.patterns.hlhp_patterns_engine import EnvDay, check_pattern_alerts
from app.hlhp.patterns.hlhp_patterns_prompts import pattern_alert_copy
from app.hlhp.services.pattern_state_store import get_pattern_alerts, save_pattern_alerts
from app.hlhp.services.patterns_lifecycle_service import enqueue_pattern_alert_pushes
from app.hlhp.services.scan_log_store import fetch_scans
from app.hlhp.services.weatherapi_forecast import fetch_weatherapi_forecast

logger = logging.getLogger(__name__)


def _forecast_to_env_map(readings, *, city: str) -> dict[date, EnvDay]:
    out: dict[date, EnvDay] = {}
    for row in readings:
        try:
            day = date.fromisoformat(row.date)
        except ValueError:
            continue
        env = EnvironmentalData(
            uv_index=float(row.uv_index),
            temperature_c=float(row.temp_c),
            aqi=int(row.aqi),
            humidity_pct=float(row.humidity_pct),
            location_name=city,
        )
        bands = bands_snapshot(bucketize_environment(env))
        out[day] = EnvDay(
            city=city,
            day=day,
            band_keys={
                "temp": bands["temp_band"],
                "uv": bands["uv_band"],
                "humidity": bands["humidity_band"],
                "aqi": bands["aqi_band"],
            },
        )
    return out


async def _latest_coords(user_id: str) -> tuple[float, float, str] | None:
    since = datetime.now(timezone.utc) - timedelta(days=14)
    scans = await fetch_scans(user_id, since=since, limit=20)
    for scan in scans:
        lat = scan.get("latitude")
        lon = scan.get("longitude")
        if lat is not None and lon is not None:
            city = str(scan.get("city") or "")
            return float(lat), float(lon), city
    return None


async def run_pattern_alert_forecast(user_id: str, *, today: date | None = None) -> int:
    """Check subscribed patterns against 2-day forecast when the user is active."""
    today = today or today_local()
    alerts = await get_pattern_alerts(user_id)
    active = [a for a in alerts if a.active]
    if not active:
        return 0

    coords = await _latest_coords(user_id)
    if coords is None:
        return 0
    lat, lon, city = coords
    readings = await fetch_weatherapi_forecast(lat, lon, days=3)
    if not readings:
        return 0

    forecast_env = _forecast_to_env_map(readings, city=city)
    fired = check_pattern_alerts(
        active,
        forecast_env,
        {"surge": True},
        today,
        horizon_days=2,
    )
    if not fired:
        return 0

    await save_pattern_alerts(user_id, alerts)
    outbox_items = []
    for item in fired:
        copy = pattern_alert_copy(
            item.get("driver", ""),
            item.get("symptom", ""),
            str(item.get("when", "soon")),
        )
        outbox_items.append({**item, "user_id": user_id, "copy": copy})
    await enqueue_pattern_alert_pushes(outbox_items)
    return len(outbox_items)
