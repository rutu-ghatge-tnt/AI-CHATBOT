"""Alert quality gates — empty L1, env mismatch, did-you-know copy."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.season import indian_season
from app.hlhp.evidence.alert_quality import (
    effective_l1,
    is_consumer_copy,
    is_publishable_finding,
    pick_did_you_know,
    pick_display_l2,
    temp_copy_penalty,
)
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.models import EvidenceFinding
from app.hlhp.evidence.ranker import rank_findings, select_fire_budget
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.scan_service import _finding_to_tile


def _env(**kwargs):
    defaults = dict(
        uv_index=0.5,
        temperature_c=28.2,
        aqi=145,
        humidity_pct=72.0,
        location_name="Pune",
        fetched_at=datetime.now(),
        data_sources={},
        raw_weather_payload={},
        weather_api_url="https://example.org",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def _acne_profile() -> UserProfile:
    return UserProfile(
        user_id="test-user",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )


def test_lif_340_not_publishable_evening():
    store = get_evidence_store()
    lif340 = next(f for f in store.findings if f.id == "LIF-340")
    assert not is_publishable_finding(lif340, guest_mode=False, day_phase="evening")


def test_warm_evening_penalises_cold_air_copy():
    store = get_evidence_store()
    tem2 = next(f for f in store.findings if f.id == "TEM-2")
    penalty = temp_copy_penalty(
        tem2, "warm", guest_mode=False, day_phase="evening"
    )
    assert penalty < -100


def test_acne_warm_evening_headlines_non_empty_and_no_lif340():
    store = get_evidence_store()
    env = _env()
    bands = bucketize_environment(env)
    profile = _acne_profile()
    candidates = match_findings(
        store.findings,
        season=indian_season(),
        bands=bands,
        profile=profile,
        guest_mode=False,
        index=store.index,
        day_phase="evening",
    )
    ranked = rank_findings(
        candidates,
        profile=profile,
        day_phase="evening",
        guest_mode=False,
        bands=bands,
    )
    headlines, _ = select_fire_budget(
        ranked, guest_mode=False, day_phase="evening", headline_slots=3
    )
    assert headlines, "expected at least one headline"
    assert all(
        is_publishable_finding(h, guest_mode=False, day_phase="evening") for h in headlines
    )
    assert "LIF-340" not in {h.id for h in headlines}
    assert "TEM-2" not in {h.id for h in headlines[:1]}


def test_finding_to_tile_skips_bullet_did_you_know():
    store = get_evidence_store()
    lif340 = next(f for f in store.findings if f.id == "LIF-340")
    # Use a finding with real L1 for tile assembly test
    tem2 = next(f for f in store.findings if f.id == "TEM-2")
    bands = bucketize_environment(_env())
    tile = _finding_to_tile(
        tem2,
        guest_mode=False,
        day_phase="evening",
        bands=bands,
        glossary=store.glossary,
    )
    assert tile.l1
    assert ";" not in (tile.did_you_know or "")
    if tile.did_you_know:
        assert is_consumer_copy(tile.did_you_know)


def test_pick_did_you_know_differs_from_l2_bullets():
    f = EvidenceFinding.from_dict(
        {
            "id": "TST-DYK",
            "factor": "Lifestyle",
            "row_number": 1,
            "sub_effect": "monsoon",
            "quantified": "",
            "mechanism": "",
            "product_implication": "season-aware pediatric routines; anti-fungal cleanser monsoon",
            "outcome_tag": "",
            "confidence": "",
            "india_relevant": True,
            "source_type": "Book",
            "source_title": "T",
            "edition_year": "",
            "chapter_section": "",
            "pages_doi_pmid": "p1",
            "alert_short": "",
            "priority": "P2",
            "triggers": {
                "season": ["any"],
                "uvi": ["any"],
                "aqi": ["any"],
                "rh": ["any"],
                "temp": ["any"],
                "user_filter": [],
            },
            "alert_l1_personalised": "Monsoon humidity is stacking on your acne-prone skin tonight.",
            "alert_l1_guest": "",
            "never_fire": False,
            "science_citation": "",
            "physical_analogy": "Think of your pores like clogged drains after heavy rain.",
        }
    )
    l2 = pick_display_l2(f)
    dyk = pick_did_you_know(f, l2=l2)
    assert "pediatric" in l2.lower() or ";" in l2
    assert dyk == "Think of your pores like clogged drains after heavy rain."
