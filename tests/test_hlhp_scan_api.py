"""Tests for HLHP v2 scan API and Outdoor-OK scorer."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.scan import ScanRequest, SymptomTapRequest
from app.hlhp.services.outdoor_ok import compute_outdoor_ok, uv_penalty
from app.hlhp.services.scan_service import run_scan, run_symptom_tap


def _env_data(**kwargs):
    defaults = dict(
        uv_index=8.0,
        temperature_c=32.0,
        aqi=120,
        humidity_pct=55.0,
        location_name="Mumbai",
        fetched_at=datetime.now(),
        data_sources={},
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def test_outdoor_ok_penalties():
    score, band = compute_outdoor_ok(
        _env_data(uv_index=0, aqi=40, temperature_c=22, humidity_pct=50)
    )
    assert score >= 95
    assert "Easy" in band

    harsh, band_h = compute_outdoor_ok(
        _env_data(uv_index=11, aqi=400, temperature_c=39, humidity_pct=20)
    )
    assert harsh < 25
    assert "Hard" in band_h


def test_uv_penalty_monotonic():
    assert uv_penalty(0) == 0
    assert uv_penalty(11) == 60
    assert uv_penalty(5) < uv_penalty(9)


def test_run_scan_guest_with_raw_env():
    req = ScanRequest(
        user_id=None,
        city="Mumbai",
        local_time=datetime(2026, 6, 18, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        raw_uvi=8.0,
        raw_aqi=145,
        raw_rh=72.0,
        raw_temp=31.0,
    )
    resp = asyncio.run(run_scan(req))
    assert resp.mode == "guest"
    assert resp.profile_nudge
    assert resp.outdoor_ok_score >= 0
    assert resp.env_snapshot.uvi_band == "very_high"
    assert len(resp.alerts) <= 3
    assert len(resp.candidate_alerts) <= 5
    if resp.alerts:
        assert resp.alerts[0].l1
        assert resp.alerts[0].rule_id
        assert resp.alerts[0].severity in {"BLOCK_ENV", "HARD_ENV", "SOFT_ENV"}


def test_hlhp_health_store_loaded():
    store = get_evidence_store()
    assert store.version >= 2
    assert len(store.findings) >= 1000


def test_symptom_tap_guest():
    req = SymptomTapRequest(
        user_id=None,
        symptom_keyword="oily",
        city="Mumbai",
        local_time=datetime(2026, 6, 18, 14, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        raw_uvi=8.0,
        raw_aqi=120,
        raw_rh=70.0,
        raw_temp=32.0,
    )
    resp = asyncio.run(run_symptom_tap(req))
    assert resp.headline
    assert resp.decode_text
