"""In-app city-env board collector — runs while the FastAPI process is up (no OS cron).

Enabled by default when WEATHERAPI_KEY is set. Disable with HLHP_CITY_ENV_SCHEDULER=0.
Skips work when yesterday+today board rows are already complete (11 cities).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.hlhp.services.city_env_collector import ist_today_yesterday
from app.hlhp.services.city_env_store import CITY_ENV_DAILY, CITY_ENV_TZ

logger = logging.getLogger(__name__)

_IST = ZoneInfo(CITY_ENV_TZ)
_BOARD_SIZE = 11
_task: Optional[asyncio.Task] = None
_lock = asyncio.Lock()


def scheduler_enabled() -> bool:
    raw = (os.getenv("HLHP_CITY_ENV_SCHEDULER") or "1").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    from app.hlhp.config import hl_settings

    return bool(hl_settings.WEATHERAPI_KEY)


def poll_seconds() -> int:
    """How often to wake and check (default 1 hour)."""
    try:
        return max(300, int(os.getenv("HLHP_CITY_ENV_POLL_SECONDS", "3600")))
    except ValueError:
        return 3600


async def _board_day_complete(date_iso: str) -> bool:
    from app.hlhp.db import hl_db

    try:
        n = await hl_db[CITY_ENV_DAILY].count_documents(
            {"date": date_iso, "on_board": True, "ok": True}
        )
        return n >= _BOARD_SIZE
    except Exception as exc:
        logger.warning("HLHP city-env completeness check failed: %s", exc)
        return False


async def board_archive_fresh() -> bool:
    today_iso, yday_iso = ist_today_yesterday()
    return await _board_day_complete(yday_iso) and await _board_day_complete(today_iso)


def _in_preferred_window() -> bool:
    """Prefer evening IST (after 21:00 slot) or overnight; still allow catch-up anytime if gaps."""
    hour = datetime.now(_IST).hour
    return hour >= 21 or hour < 8


async def run_board_collect_if_needed(*, force: bool = False) -> dict | None:
    """Single-flight board collect. Returns summary or None if skipped."""
    if not scheduler_enabled() and not force:
        return None

    async with _lock:
        if not force and await board_archive_fresh():
            logger.info("HLHP city-env board already complete for yesterday+today — skip")
            return None
        if not force and not _in_preferred_window():
            # Outside window: only run if yesterday is missing (catch-up).
            _, yday_iso = ist_today_yesterday()
            if await _board_day_complete(yday_iso):
                logger.debug("HLHP city-env: outside preferred window and yesterday ok — wait")
                return None

        from app.hlhp.services.city_env_jobs import collect_fixed_board

        logger.info("HLHP city-env board collect starting")
        summary = await collect_fixed_board()
        logger.info(
            "HLHP city-env board collect done ok_day_writes=%s",
            summary.get("ok_day_writes"),
        )
        return summary


async def _scheduler_loop() -> None:
    # Let Mongo / weather settle after boot.
    await asyncio.sleep(45)
    while True:
        try:
            await run_board_collect_if_needed()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("HLHP city-env scheduler tick failed: %s", exc)
        await asyncio.sleep(poll_seconds())


def start_city_env_scheduler() -> None:
    global _task
    if not scheduler_enabled():
        logger.info("HLHP city-env scheduler disabled (HLHP_CITY_ENV_SCHEDULER=0 or no weather key)")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_scheduler_loop(), name="hlhp_city_env_scheduler")
    logger.info(
        "HLHP city-env scheduler started (poll=%ss, preferred window IST 21:00–08:00)",
        poll_seconds(),
    )


async def stop_city_env_scheduler() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    logger.info("HLHP city-env scheduler stopped")
