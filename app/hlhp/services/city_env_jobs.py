"""Board + off-board city env collection jobs (AI-Tools owned)."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.hlhp.services.city_chart_service import CITY_QUERIES, fetch_weatherapi_day_payload
from app.hlhp.services.city_env_collector import (
    ist_today_yesterday,
    iter_ist_dates,
    persist_city_env_from_payload,
)
from app.hlhp.services.city_env_store import CITY_ENV_TZ, list_recent_off_board_cities

logger = logging.getLogger(__name__)

_IST = ZoneInfo(CITY_ENV_TZ)
_FETCH_SEM = asyncio.Semaphore(4)


async def _persist_query_dates(
    *,
    city_label: str,
    query: str,
    dates: list[str],
    today_iso: str,
    on_board: bool,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    # Chronological so each day's yesterday_sfi can chain when consecutive.
    prev_sfi: int | None = None
    for date_iso in dates:
        async with _FETCH_SEM:
            payload = await fetch_weatherapi_day_payload(
                query, date_iso, today_iso=today_iso
            )
        summary = await persist_city_env_from_payload(
            city_label=city_label,
            query=query,
            date_iso=date_iso,
            payload=payload,
            on_board=on_board,
            yesterday_sfi=prev_sfi,
        )
        if summary.get("ok") and summary.get("sfi_env") is not None:
            prev_sfi = int(summary["sfi_env"])
        else:
            prev_sfi = None
        summaries.append(summary)
    return summaries


async def collect_fixed_board(
    *,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert slot+daily rows for the fixed 11-city board."""
    today_iso, _ = ist_today_yesterday()
    if not dates:
        # Default: yesterday + today (complete delta + latest day).
        yday = (datetime.now(_IST).date() - timedelta(days=1)).isoformat()
        dates = [yday, today_iso]

    results: list[dict[str, Any]] = []
    for city, query in CITY_QUERIES.items():
        try:
            city_summaries = await _persist_query_dates(
                city_label=city,
                query=query,
                dates=dates,
                today_iso=today_iso,
                on_board=True,
            )
            results.append({"city": city, "days": city_summaries})
        except Exception as exc:
            logger.warning("HLHP board collect failed for %s: %s", city, exc)
            results.append({"city": city, "error": str(exc)})

    ok_days = sum(
        1
        for row in results
        for day in (row.get("days") or [])
        if isinstance(day, dict) and day.get("ok")
    )
    return {
        "cities": len(CITY_QUERIES),
        "dates": dates,
        "ok_day_writes": ok_days,
        "results": results,
    }


async def collect_off_board_recent(*, lookback_days: int = 7) -> dict[str, Any]:
    """Refresh off-board cities seen recently (12th-city archive)."""
    today_iso, _ = ist_today_yesterday()
    since = (datetime.now(_IST).date() - timedelta(days=lookback_days)).isoformat()
    keys = await list_recent_off_board_cities(since_date=since, limit=40)
    yday = (datetime.now(_IST).date() - timedelta(days=1)).isoformat()
    dates = [yday, today_iso]
    results: list[dict[str, Any]] = []
    for key in keys:
        label = key.replace("_", " ").title()
        query = f"{label},India"
        try:
            days = await _persist_query_dates(
                city_label=label,
                query=query,
                dates=dates,
                today_iso=today_iso,
                on_board=False,
            )
            results.append({"city": label, "city_key": key, "days": days})
        except Exception as exc:
            logger.warning("HLHP off-board collect failed for %s: %s", key, exc)
            results.append({"city_key": key, "error": str(exc)})
    return {"cities": len(keys), "dates": dates, "results": results}


async def backfill_fixed_board(*, days: int = 30) -> dict[str, Any]:
    """History backfill for the fixed board (IST dates ending today)."""
    end = datetime.now(_IST).date()
    start = end - timedelta(days=max(1, days) - 1)
    dates = iter_ist_dates(start, end)
    return await collect_fixed_board(dates=dates)
