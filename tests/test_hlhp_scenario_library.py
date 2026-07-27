"""Tests for scenario library engine."""

from datetime import datetime
from zoneinfo import ZoneInfo

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
    time_window_for_datetime,
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


def test_scenario_store_loads_v36():
    store = get_scenario_store()
    assert store.version == "3.7"
    assert store.master_cell_count == 1140
    assert store.compound_cell_count == 940
    assert store.guest_cell_count >= 200
    assert len(store.gender_states) == 9
    assert len(store.gender_rules) == 40
    assert len(store.age_rules) == 36
    assert len(store.routine_rules) == 28
    assert len(store.time_overlay) == 25
    assert store.bands.get("UV")


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
    assert resp.scenario_library_version == "3.7"


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
    assert result.flash_alert.l0
    assert result.cell_kind in {"master", "compound"}
    assert result.evidence_cell is not None
    assert result.evidence_cell.confidence in {"HIGH", "MODERATE", "LOW"}


def test_gender_rule_adjusts_risk_and_copy_not_sfi():
    store = get_scenario_store()
    env = _env(uv_index=4.0, temperature_c=28, humidity_pct=52, aqi=80)
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
        life_stage="Female + PCOS",
    )
    adjusted = evaluate_scenario(
        store, env, city="Pune", profile=profile, guest_mode=False
    )
    baseline = evaluate_scenario(
        store,
        env,
        city="Pune",
        profile=UserProfile(
            user_id="u1",
            skin_type=SkinType.OILY,
            skin_concerns=[SkinConcern.ACNE],
            gender=Gender.FEMALE,
            age_bracket=AgeBracket.AGE_25_30,
            life_stage="Female",
        ),
        guest_mode=False,
    )
    # Environmental band-sum SFI in evaluate_scenario is life-stage free.
    assert adjusted.sfi == baseline.sfi
    assert adjusted.risk >= baseline.risk
    assert "testosterone" in adjusted.flash_alert.l1.lower() or adjusted.flash_alert.tip

def test_time_overlay_appends_morning_clause():
    store = get_scenario_store()
    env = _env(uv_index=4.0, temperature_c=28, humidity_pct=52, aqi=80)
    morning = evaluate_scenario(
        store,
        env,
        city="Pune",
        profile=None,
        guest_mode=True,
        local_time=datetime(2026, 6, 18, 8, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    midday = evaluate_scenario(
        store,
        env,
        city="Pune",
        profile=None,
        guest_mode=True,
        local_time=datetime(2026, 6, 18, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert morning.time_window == "morning"
    assert midday.time_window == "daytime"
    assert len(morning.flash_alert.l1) > len(midday.flash_alert.l1)
    assert "afternoon" in morning.flash_alert.l1.lower()


def test_time_window_for_datetime_matches_three_window_model():
    assert time_window_for_datetime(datetime(2026, 6, 18, 8, 0)) == "morning"
    assert time_window_for_datetime(datetime(2026, 6, 18, 12, 0)) == "daytime"
    assert time_window_for_datetime(datetime(2026, 6, 18, 18, 0)) == "evening"


def test_months_for_season_spec_parses_ranges_and_wrap():
    from app.hlhp.services.scenario_engine import months_for_season_spec

    assert months_for_season_spec("Apr–Jun") == {4, 5, 6}
    assert months_for_season_spec("Jul–Sep") == {7, 8, 9}
    assert months_for_season_spec("Nov–Jan") == {11, 12, 1}
    assert months_for_season_spec("Mar–May, Oct–Nov") == {3, 4, 5, 10, 11}
    assert months_for_season_spec("Jun (early)") == {6}
    assert months_for_season_spec("any") is None
    assert months_for_season_spec("year-round (office workers)") is None


def test_july_does_not_select_pre_monsoon_sun_heat():
    """Regression: compound matching used to ignore nested bands + seasons."""
    from datetime import date

    from app.hlhp.services.scenario_engine import match_compound_index, driver_states

    store = get_scenario_store()
    # Hot + very high UV + moderate AQI + low RH — C01 band fingerprint.
    env = _env(temperature_c=36.0, uv_index=9.0, aqi=150, humidity_pct=30.0)
    drivers = driver_states(store, env)

    may = match_compound_index(store, drivers, zone="CN", when=date(2026, 5, 15))
    july = match_compound_index(store, drivers, zone="CN", when=date(2026, 7, 23))

    assert may is not None
    assert may["name"] == "Pre-Monsoon Sun & Heat"
    assert july is None or july["name"] != "Pre-Monsoon Sun & Heat"

    july_eval = evaluate_scenario(
        store,
        env,
        city="Delhi",
        profile=None,
        guest_mode=True,
        local_time=datetime(2026, 7, 23, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert "Pre-Monsoon" not in (july_eval.flash_alert.l0 or "")
    assert july_eval.compound_name != "Pre-Monsoon Sun & Heat"


def test_age_rules_adjust_cell_risk_not_sfi():
    from app.hlhp.services.sfi_unified import resolve_life_stage_adjustment, resolve_sfi

    store = get_scenario_store()
    rule = store.age_rules.get("young_adult|acne")
    assert rule is not None
    assert isinstance(rule.get("risk_delta"), (int, float))

    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_18_24,
    )
    env = _env(temperature_c=28, uv_index=6, humidity_pct=52, aqi=80)
    scored = resolve_sfi(env, profile, guest_mode=False)
    adj = resolve_life_stage_adjustment(2, profile, guest_mode=False, concern="Acne")

    assert scored.personal_sfi is not None
    # Age/gender must not be baked into the SFI arithmetic.
    assert scored.personal_sfi == scored.environmental_sfi - scored.rho_concern - scored.rho_skin
    expected = max(0, min(5, 2 + int(adj.gender_delta) + int(adj.age_delta)))
    assert adj.adjusted_risk == expected
    assert adj.age_rule_found or adj.gender_rule_found or adj.coverage_gap
