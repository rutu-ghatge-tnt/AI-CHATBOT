"""Shared HTTP helpers that count weather-provider usage for ops alerts."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.hlhp.services import weather_quota

logger = logging.getLogger(__name__)


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 12,
    provider: str,
) -> dict | None:
    """GET JSON; record success / 403-429 toward weather quota alerts."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
        if resp.status_code in (403, 429):
            await weather_quota.note_http_error(
                provider, resp.status_code, detail=resp.text[:300]
            )
            logger.warning(
                "%s HTTP %s (%s)", provider, resp.status_code, url
            )
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
