"""Tests for v3.4 scenario library engine."""

from datetime import datetime

from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.scenario_engine import (
    CONCERN_TO_LIBRARY,
    band_for_sfi,
    compute_sfi,
    evaluate_scenario,
    lookup_master_cell,
    driver_states,
    resolve_library_concerns,
)
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile


def _env(**kwargs):
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


def test_scenario_store_loads_v34():
    store = get_scenario_store()
    assert store.version == "3.4"
    assert store.master_cell_count == 880
    assert store.compound_cell_count == 670
    assert store.guest_cell_count >= 200


def test_guest_mode_uses_none_concern_cells():
    store = get_scenario_store()
    env = _env()
    result = evaluate_scenario(store, env, city="Delhi", profile=None, guest_mode=True)
    assert result.concern == "None"
    assert result.skin == "Normal"
    assert result.cell_kind in {"guest_single", "guest_compound"}
    assert result.flash_alert.l0


def test_sfi_is_sum_of_band_points():
    store = get_scenario_store()
    env = _env(temperature_c=28, uv_index=6, humidity_pct=52, aqi=80)
    drivers = driver_states(store, env)
    assert compute_sfi(store, env) == sum(d.points for d in drivers)
    assert 0 <= compute_sfi(store, env) <= 100


def test_band_for_sfi_matches_ui_ramp():
    assert band_for_sfi(90) == "Paradise Mode"
    assert band_for_sfi(75) == "Smooth Sailing"
    assert band_for_sfi(60) == "Guard Up"
    assert band_for_sfi(45) == "Battle Stations"
    assert band_for_sfi(30) == "Hostile Mode"
    assert band_for_sfi(10) == "Code Red"


def test_master_cell_lookup_for_mumbai_guest():
    store = get_scenario_store()
    env = _env()
    result = evaluate_scenario(store, env, city="Mumbai", profile=None, guest_mode=True)
    assert result.sfi > 0
    assert result.flash_alert.l0
    assert result.flash_alert.l1
    assert result.evidence_cell is not None
    assert result.evidence_cell.factor


def test_run_scan_includes_scenario_fields():
    import asyncio
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.hlhp.models.scan import ScanRequest
    from app.hlhp.services.scan_service import run_scan

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
    assert resp.sfi is not None
    assert resp.band
    assert resp.flash_alert is not None
    assert resp.flash_alert.l0
    assert resp.evidence_cell is not None
    assert resp.scenario_library_version == "3.4"


def test_lookup_master_cell_key_format():
    store = get_scenario_store()
    env = _env(temperature_c=32, uv_index=7, humidity_pct=82, aqi=120)
    drivers = driver_states(store, env)
    cell = lookup_master_cell(store, drivers, "Combination", "Acne")
    assert cell is not None
    assert cell.get("l0")
    assert cell.get("l1")


def test_concern_to_library_covers_all_skin_concerns():
    for concern in SkinConcern:
        assert concern in CONCERN_TO_LIBRARY, f"missing library map for {concern}"


def test_resolve_library_concerns_uses_secondary_when_primary_unmapped_cell():
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.PORES, SkinConcern.DEHYDRATION],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    concerns = resolve_library_concerns(profile, guest_mode=False)
    assert concerns == ["Oily Skin", "Dryness"]


def test_personalised_scan_uses_profile_concern_cell():
    store = get_scenario_store()
    env = _env(humidity_pct=88, temperature_c=28, uv_index=0.6, aqi=55)
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.DEHYDRATION],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    result = evaluate_scenario(
        store, env, city="Mumbai", profile=profile, guest_mode=False
    )
    assert result.concern == "Dryness"
    assert result.cell is not None
    assert "humid" in result.flash_alert.l0.lower()
    assert result.evidence_cell is not None
    assert result.evidence_cell.confidence in {"HIGH", "MODERATE", "LOW"}
