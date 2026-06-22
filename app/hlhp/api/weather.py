"""Proxy Skintruth location-weather (background + animal assets for home strip)."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.hlhp.config import hl_settings

router = APIRouter(tags=["Weather"])


@router.get("/v1/weathers/location-weather")
async def location_weather(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    """
    Pass-through to Skintruth location-weather.
    Used by the home weather strip for backgroundImage + animal (screenVariants).
    """
    params = {"latitude": latitude, "longitude": longitude}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(hl_settings.WEATHER_API_URL, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.text[:500] or "Weather upstream error",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weather fetch failed: {exc}") from exc
