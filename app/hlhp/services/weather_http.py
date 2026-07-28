"""Shared HTTP helpers that count weather-provider usage for ops alerts."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.hlhp.config import hl_settings
from app.hlhp.services import weather_quota
from app.hlhp.services.weather_quota import PROVIDER_OPEN_METEO

logger = logging.getLogger(__name__)

# Process-wide gate for Open-Meteo (free tier rejects parallel bursts).
_open_meteo_sem: asyncio.Semaphore | None = None
_open_meteo_sem_limit: int | None = None
_open_meteo_last_at: float = 0.0


def _open_meteo_semaphore() -> asyncio.Semaphore:
    global _open_meteo_sem, _open_meteo_sem_limit
    limit = max(1, int(hl_settings.OPEN_METEO_MAX_CONCURRENT))
    if _open_meteo_sem is None or _open_meteo_sem_limit != limit:
        _open_meteo_sem = asyncio.Semaphore(limit)
        _open_meteo_sem_limit = limit
    return _open_meteo_sem


async def _pace_open_meteo() -> None:
    """Space requests so free-tier concurrency + burst limits are respected."""
    global _open_meteo_last_at
    gap_ms = max(0, int(hl_settings.OPEN_METEO_MIN_INTERVAL_MS))
    if gap_ms <= 0:
        return
    now = time.monotonic()
    wait = (gap_ms / 1000.0) - (now - _open_meteo_last_at)
    if wait > 0:
        await asyncio.sleep(wait)


async def _mark_open_meteo_done() -> None:
    global _open_meteo_last_at
    _open_meteo_last_at = time.monotonic()


async def _do_get_json(
    url: str,
    *,
    params: dict[str, Any] | None,
    timeout: float,
    provider: str,
) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
        if resp.status_code in (403, 429):
            await weather_quota.note_http_error(
                provider, resp.status_code, detail=resp.text[:300]
            )
            logger.warning("%s HTTP %s (%s)", provider, resp.status_code, url)
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            await weather_quota.note_success(provider)
            return data
        return None
    except Exception as exc:
        logger.warning("%s request failed (%s): %s", provider, url, exc)
        return None


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 12,
    provider: str,
) -> dict | None:
    """GET JSON; record success / 403-429 toward weather quota alerts.

    Open-Meteo calls are serialized (default concurrency 1) with optional spacing
    so city-board gathers cannot trip "Too many concurrent requests".
    """
    if provider == PROVIDER_OPEN_METEO:
        async with _open_meteo_semaphore():
            await _pace_open_meteo()
            try:
                return await _do_get_json(
                    url, params=params, timeout=timeout, provider=provider
                )
            finally:
                await _mark_open_meteo_done()
    return await _do_get_json(url, params=params, timeout=timeout, provider=provider)
