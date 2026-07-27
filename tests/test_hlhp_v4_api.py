"""HLHP V4 API + unified SFI integration tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.models.scan import ScanRequest
from app.hlhp.models.v4_api import V4LogRequest
from app.hlhp.services.scan_service import run_scan
from app.hlhp.services.sfi_unified import resolve_sfi
from app.hlhp.services.v4_api_service import (
    _share_caption,
    assemble_recap,
    assemble_today,
)

IST = ZoneInfo("Asia/Kolkata")


def _env(**kwargs) -> EnvironmentalData:
    defaults = dict(
        uv_index=6.0,
        temperature_c=28.0,
        aqi=80,
        humidity_pct=52.0,
        wind_kmh=10.0,
        location_name="Pune",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def test_unified_sfi_matches_weighted_engine():
    eval_ = resolve_sfi(_env(), None, guest_mode=True)
    assert eval_.environmental_sfi == 64
    assert eval_.mode == "Guard Up"


def test_scan_uses_v4_sfi_and_scene():
    req = ScanRequest(
        user_id=None,
        city="Pune",
        local_time=datetime(2026, 7, 8, 9, 0, tzinfo=IST),
        raw_uvi=6.0,
        raw_aqi=80,
        raw_rh=52.0,
        raw_temp=28.0,
    )
    resp = asyncio.run(run_scan(req))
    assert resp.sfi == 64
    assert resp.band == "Guard Up"
    assert resp.outdoor_ok_score == 64
    assert resp.scene in {"clear", "rain", "windy", "heat", "haze", "snow", "storm"}
    assert len(resp.impacts) == 4


def test_v4_today_payload_shape():
    resp = asyncio.run(
        assemble_today(
            user_id=None,
            city="Pune",
            local_time=datetime(2026, 7, 8, 9, 0, tzinfo=IST),
            raw_uvi=6.0,
            raw_aqi=80,
            raw_rh=52.0,
            raw_temp=28.0,
        )
    )
    assert resp.city
    assert resp.date == "2026-07-08"
    assert resp.mode_of_use == "guest"
    assert resp.sfi.environmental == 64
    assert resp.sfi.headline == 64
    assert len(resp.drivers) == 4
    assert resp.alert.l0 or resp.alert.l1
    assert resp.weather.wind_kmh >= 0
    assert resp.adverse is False or resp.adverse is True
    assert isinstance(resp.adverse_tags, list)


def test_share_caption_en_in_format():
    from datetime import date

    caption = _share_caption(
        week_avg=72,
        trend=4,
        city="Pune",
        week_start=date(2026, 7, 2),
        week_end=date(2026, 7, 8),
    )
    assert "2 Jul" in caption
    assert "8 Jul" in caption
    assert "72/100" in caption
    assert "+4" in caption
    assert "Pune" in caption


def test_v4_recap_month_structure():
    async def _run():
        with patch(
            "app.hlhp.services.v4_api_service.fetch_daily_logs",
            new=AsyncMock(return_value=[]),
        ):
            return await assemble_recap("test-user", "2026-07")

    recap = asyncio.run(_run())
    assert recap.month == "2026-07"
    assert len(recap.days) == 31


def test_feeling_log_is_not_an_sfi_input():
    import app.hlhp.services.v4_scoring_engine as engine

    assert not hasattr(engine, "feeling_log_sfi_adjustment")


def test_life_stage_adjusts_cell_risk_not_sfi():
    from app.hlhp.services.sfi_unified import resolve_life_stage_adjustment, resolve_sfi

    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_18_24,
    )
    env = _env()
    score = resolve_sfi(env, profile, guest_mode=False)
    adj = resolve_life_stage_adjustment(2, profile, guest_mode=False, concern="Acne")
    # SFI path must not accept life-stage kwargs; risk path may move 0-5 risk.
    assert 0 <= adj.adjusted_risk <= 5
    assert score.personal_sfi is not None
    assert score.personal_sfi == score.environmental_sfi - score.rho_concern - score.rho_skin


def test_v4_log_request_rejects_normal_with_others():
    with pytest.raises(ValueError, match="exclusive"):
        V4LogRequest(
            user_id="u1",
            symptoms=["normal", "oily"],
            areas=[],
        )


def test_v4_log_request_requires_areas_for_breakout():
    with pytest.raises(ValueError, match="areas required"):
        V4LogRequest(
            user_id="u1",
            symptoms=["breakout"],
            areas=[],
        )


class TestV4HttpRoutes:
    def test_today_route_registered(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/v2/today",
                    params={
                        "city": "Pune",
                        "raw_uvi": 6,
                        "raw_aqi": 80,
                        "raw_rh": 52,
                        "raw_temp": 28,
                    },
                )
                return resp

        resp = asyncio.run(_call())
        assert resp.status_code == 200
        data = resp.json()
        assert data["sfi"]["environmental"] == 64
        assert "scene" in data
        assert "drivers" in data

    def test_streak_route_requires_auth(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get("/api/v2/streak", params={"user_id": "u1"})

        resp = asyncio.run(_call())
        assert resp.status_code in {401, 403, 422}
