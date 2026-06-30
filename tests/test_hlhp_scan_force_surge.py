"""Tests for force_surge on scan API."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.hlhp.models.scan import ScanRequest
from app.hlhp.services.scan_service import run_scan


def test_force_surge_lowers_sfi_without_changing_env_snapshot():
    base = ScanRequest(
        user_id=None,
        city="Mumbai",
        local_time=datetime(2026, 6, 18, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        raw_uvi=6.0,
        raw_aqi=80,
        raw_rh=55.0,
        raw_temp=28.0,
    )
    normal = asyncio.run(run_scan(base))
    surged = asyncio.run(run_scan(base.model_copy(update={"force_surge": True})))

    assert surged.sfi is not None and normal.sfi is not None
    assert surged.sfi < normal.sfi
    assert surged.env_snapshot.temp_c == normal.env_snapshot.temp_c
    assert surged.env_snapshot.uvi == normal.env_snapshot.uvi
    assert surged.flash_alert is not None
    assert surged.sudden_event_tags
