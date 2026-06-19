"""Tests for HLHP v2 evidence fields and phase-aware selection."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.hlhp.core.phase import resolve_day_phase
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.models import EvidenceFinding
from app.hlhp.evidence.selector import select_evidence_bundle
from app.hlhp.models.environmental import EnvironmentalData


def _env(**kwargs):
    defaults = dict(
        uv_index=8.0,
        temperature_c=32.0,
        aqi=120,
        humidity_pct=55.0,
        location_name="Mumbai",
        fetched_at=datetime.now(),
        data_sources={},
        raw_weather_payload={},
        weather_api_url="https://example.org",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def test_snapshot_v2_has_engagement_fields():
    store = get_evidence_store()
    assert store.version >= 2
    sample = store.findings[0]
    assert hasattr(sample, "alert_l2_explainer")
    assert hasattr(sample, "time_of_day_phase")
    assert hasattr(sample, "mood_verdict_tag")
    assert hasattr(sample, "routine_action")


def test_finding_pick_l1_evening_fallback():
    f = EvidenceFinding.from_dict(
        {
            "id": "TST-1",
            "factor": "UV",
            "row_number": 1,
            "sub_effect": "test",
            "quantified": "",
            "mechanism": "",
            "product_implication": "",
            "outcome_tag": "",
            "confidence": "",
            "india_relevant": True,
            "source_type": "Book",
            "source_title": "T",
            "edition_year": "",
            "chapter_section": "",
            "pages_doi_pmid": "p1",
            "alert_short": "",
            "priority": "P0",
            "triggers": {
                "season": ["any"],
                "uvi": ["any"],
                "aqi": ["any"],
                "rh": ["any"],
                "temp": ["any"],
                "user_filter": [],
            },
            "alert_l1_personalised": "Morning line",
            "alert_l1_guest": "Guest morning",
            "alert_l1_evening_personalised": "Evening line",
            "alert_l1_evening_guest": "Guest evening",
            "never_fire": False,
            "science_citation": "",
        }
    )
    assert f.pick_l1(guest_mode=False, day_phase="evening") == "Evening line"
    assert f.pick_l1(guest_mode=True, day_phase="morning") == "Guest morning"


def test_internal_only_rows_excluded_from_matching():
    store = get_evidence_store()
    internal = [f for f in store.findings if f.internal_only]
    assert internal, "expected internal-only rows in workbook"
    env = _env()
    bundle = select_evidence_bundle(env, guest_mode=True)
    assert bundle.primary is not None
    fired_ids = {bundle.primary.finding.id} | {c.id for c in bundle.carousel}
    assert not any(i.id in fired_ids for i in internal)


def test_resolve_day_phase_morning_vs_evening():
    morning = datetime(2026, 6, 18, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    evening = datetime(2026, 6, 18, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert resolve_day_phase(morning) == "morning"
    assert resolve_day_phase(evening) == "evening"
