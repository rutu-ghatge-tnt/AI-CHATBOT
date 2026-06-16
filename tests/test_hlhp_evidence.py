from datetime import datetime, timezone

from app.hlhp.evidence.gates import night_gate_blocks
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.selector import select_evidence_bundle, select_primary_finding
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.season import indian_season
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    SkinConcern,
    SkinType,
    UserProfile,
)
from app.hlhp.services.alert_generator import generate_alert
from app.hlhp.services.profile_personalizer import personalize_alert
from app.hlhp.services.scoring_engine import calculate_skin_score


def _make_env(**kwargs):
    defaults = dict(
        uv_index=8.9,
        temperature_c=38.9,
        aqi=128,
        humidity_pct=11,
        location_name="Test City",
        fetched_at=datetime.now(timezone.utc),
        data_sources={},
        raw_weather_payload={},
        weather_api_url="https://example.org/weather",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def _make_profile(**kwargs):
    defaults = dict(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
        hair_type=None,
        hair_concerns=[],
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


def test_night_gate_blocks_sunscreen_rows_at_uvi_off():
    store = get_evidence_store()
    blocked = [
        row
        for row in store.findings
        if night_gate_blocks(row, "off")
    ]
    assert blocked, "expected some sunscreen rows to be night-gate blocked"

    env = _make_env(uv_index=0.0, temperature_c=26.0, aqi=60, humidity_pct=55)
    selection = select_primary_finding(env, guest_mode=True)
    assert selection is not None
    assert "sunscreen" not in selection.l1_text.lower()
    assert "spf" not in selection.l1_text.lower()


def test_guest_mode_only_matches_any_user_filter_rows():
    env = _make_env()
    bands = bucketize_environment(env)
    store = get_evidence_store()
    guest_matches = match_findings(
        store.findings,
        season=indian_season(),
        bands=bands,
        guest_mode=True,
    )
    assert guest_matches
    assert all(not row.user_filter for row in guest_matches)


def test_personalized_dark_circles_uses_evidence_l1():
    env = _make_env(uv_index=8.0, temperature_c=32.0)
    score = calculate_skin_score(env)
    generic = generate_alert(env, score)
    profile = _make_profile(
        skin_concerns=[SkinConcern.DARK_CIRCLES],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    result = personalize_alert(generic, profile, env, score)
    text = result.personalized_whats_happening.lower()
    assert "under-eye" in text or "dark circles" in text
    assert "eye-care absorption" not in text


def test_pollution_alert_can_fire_at_uvi_off_after_night_gate_fix():
    env = _make_env(uv_index=0.0, temperature_c=28.0, aqi=180, humidity_pct=60)
    store = get_evidence_store()
    bands = bucketize_environment(env)
    matches = match_findings(
        store.findings,
        season=indian_season(),
        bands=bands,
        guest_mode=True,
    )
    pollution_matches = [r for r in matches if r.factor == "Pollution"]
    assert pollution_matches, "pollution rows should still fire at UVI 0"
    for row in pollution_matches:
        assert not night_gate_blocks(row, bands.uvi)


def test_index_matches_full_scan():
    env = _make_env()
    store = get_evidence_store()
    bands = bucketize_environment(env)
    season = indian_season()
    full = match_findings(
        store.findings,
        season=season,
        bands=bands,
        guest_mode=True,
        index=None,
    )
    indexed = match_findings(
        store.findings,
        season=season,
        bands=bands,
        guest_mode=True,
        index=store.index,
    )
    assert {f.id for f in full} == {f.id for f in indexed}


def test_snapshot_includes_all_workbook_sheets():
    store = get_evidence_store()
    assert store.readme.get("title")
    assert len(store.book_inventory) > 0
    assert store.coverage_matrix.get("source") == "auto-generated"
    assert store.build_report.get("coverage_report", {}).get("true_gap_count", 99) == 0


def test_evidence_bundle_includes_carousel_and_nuggets():
    env = _make_env()
    bundle = select_evidence_bundle(env, guest_mode=True, user_id="guest-test")
    assert bundle.primary is not None
    assert len(bundle.carousel) >= 1
    assert len(bundle.science_nuggets) >= 1
    assert bundle.evidence_version >= 1


def test_guest_alert_includes_full_evidence_metadata():
    env = _make_env()
    score = calculate_skin_score(env)
    alert = generate_alert(env, score)
    assert len(alert.whats_happening) > 40
    assert alert.science_source
    assert alert.evidence_primary_id
    assert alert.evidence_carousel
    assert alert.science_nuggets
    assert alert.clinical_gaps is not None
