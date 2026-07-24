"""Weather provider call counters + threshold email alerts.

WeatherAPI: monthly counter (plan quota).
Open-Meteo: daily counter (free-tier style limit).

Alerts at 70% / 90% of configured limit, plus hard 403/429 errors.
Each threshold emails at most once per period (deduped in Mongo).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from app.hlhp.config import hl_settings
from app.hlhp.services.ops_email import send_ops_email

logger = logging.getLogger(__name__)

_COL = "hlhp_weather_quota"
PROVIDER_WEATHERAPI = "weatherapi"
PROVIDER_OPEN_METEO = "open_meteo"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _period_key(provider: str, when: datetime | None = None) -> str:
    now = when or _utc_now()
    if provider == PROVIDER_WEATHERAPI:
        return f"{provider}:{now.strftime('%Y-%m')}"
    return f"{provider}:{now.strftime('%Y-%m-%d')}"


def _limit_for(provider: str) -> int:
    if provider == PROVIDER_WEATHERAPI:
        return max(1, int(hl_settings.WEATHERAPI_MONTHLY_LIMIT))
    return max(1, int(hl_settings.OPEN_METEO_DAILY_LIMIT))


def _period_label(provider: str) -> str:
    return "month" if provider == PROVIDER_WEATHERAPI else "day"


async def _col():
    from app.hlhp.db import hl_db

    return hl_db[_COL]


async def _bump(provider: str, *, delta: int = 1) -> dict[str, Any] | None:
    key = _period_key(provider)
    try:
        col = await _col()
        doc = await col.find_one_and_update(
            {"_id": key},
            {
                "$inc": {"count": int(delta)},
                "$set": {
                    "provider": provider,
                    "period": key.split(":", 1)[-1],
                    "updated_at": _utc_now(),
                },
                "$setOnInsert": {"created_at": _utc_now(), "alerts_sent": []},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc if isinstance(doc, dict) else None
    except Exception as exc:
        logger.warning("HLHP weather quota bump failed (%s): %s", provider, exc)
        return None


async def _mark_alert_sent(key: str, alert_id: str) -> bool:
    """Return True if this alert_id was newly recorded (should send email)."""
    try:
        col = await _col()
        result = await col.update_one(
            {"_id": key, "alerts_sent": {"$ne": alert_id}},
            {"$addToSet": {"alerts_sent": alert_id}},
        )
        return bool(result.modified_count)
    except Exception as exc:
        logger.warning("HLHP weather quota alert mark failed: %s", exc)
        return False


async def _maybe_threshold_email(provider: str, doc: dict[str, Any]) -> None:
    count = int(doc.get("count") or 0)
    limit = _limit_for(provider)
    pct = (100.0 * count / limit) if limit else 0.0
    key = str(doc.get("_id") or _period_key(provider))
    period = _period_label(provider)

    for threshold in (90, 70):
        if pct < threshold:
            continue
        alert_id = f"pct_{threshold}"
        if not await _mark_alert_sent(key, alert_id):
            continue
        level = "URGENT" if threshold >= 90 else "WARNING"
        subject = f"[HLHP] {level}: {provider} at {threshold}% of {period}ly limit"
        body = (
            f"Provider: {provider}\n"
            f"Period: {doc.get('period')} ({period})\n"
            f"Usage: {count} / {limit} ({pct:.1f}%)\n"
            f"Threshold: {threshold}%\n"
            f"Time (UTC): {_utc_now().isoformat()}\n\n"
            f"Action: check WeatherAPI / Open-Meteo dashboards; "
            f"consider raising limits or throttling city-board jobs.\n"
        )
        await send_ops_email(subject=subject, body=body)
        break  # one email per bump; higher threshold preferred when both crossed


async def note_success(provider: str) -> None:
    if not hl_settings.WEATHER_QUOTA_ALERTS_ENABLED:
        return
    doc = await _bump(provider, delta=1)
    if doc:
        await _maybe_threshold_email(provider, doc)


async def note_http_error(provider: str, status_code: int, detail: str = "") -> None:
    if not hl_settings.WEATHER_QUOTA_ALERTS_ENABLED:
        return
    if status_code not in (403, 429):
        return
    key = _period_key(provider)
    alert_id = f"http_{status_code}"
    # Ensure doc exists for dedupe list.
    await _bump(provider, delta=0)
    if not await _mark_alert_sent(key, alert_id):
        return
    subject = f"[HLHP] CRITICAL: {provider} HTTP {status_code} (quota/rate limit)"
    body = (
        f"Provider: {provider}\n"
        f"HTTP status: {status_code}\n"
        f"Detail: {(detail or '')[:500]}\n"
        f"Time (UTC): {_utc_now().isoformat()}\n\n"
        f"Live weather may be falling back to defaults or stale cache. "
        f"Check provider dashboard and raise plan limits if needed.\n"
    )
    await send_ops_email(subject=subject, body=body)
