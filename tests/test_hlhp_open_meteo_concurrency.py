"""Open-Meteo HTTP calls are serialized (no parallel bursts)."""

from __future__ import annotations

import asyncio
import os

from app.hlhp.services import weather_http
from app.hlhp.services.weather_quota import PROVIDER_OPEN_METEO


def test_open_meteo_requests_are_serialized(monkeypatch) -> None:
    monkeypatch.setenv("HLHP_OPEN_METEO_MAX_CONCURRENT", "1")
    monkeypatch.setenv("HLHP_OPEN_METEO_MIN_INTERVAL_MS", "0")
    # Force semaphore rebuild with new limit.
    weather_http._open_meteo_sem = None
    weather_http._open_meteo_sem_limit = None

    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def fake_do_get_json(url, *, params, timeout, provider):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return {"ok": True}

    monkeypatch.setattr(weather_http, "_do_get_json", fake_do_get_json)

    async def _run() -> int:
        await asyncio.gather(
            *[
                weather_http.get_json(
                    f"https://example.test/{i}",
                    provider=PROVIDER_OPEN_METEO,
                )
                for i in range(5)
            ]
        )
        return max_in_flight

    assert asyncio.run(_run()) == 1
