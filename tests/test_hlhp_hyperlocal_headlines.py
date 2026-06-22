"""Hyper-local personalised headline gates — no generic physiology/education rows."""

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.season import indian_season
from app.hlhp.evidence.alert_quality import is_headline_eligible
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.ranker import rank_findings, select_fire_budget
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from datetime import datetime


def _env(**kwargs):
    defaults = dict(
        uv_index=11.0,
        temperature_c=30.5,
        aqi=59,
        humidity_pct=50.0,
        location_name="Baner, Pune, Maharashtra",
        fetched_at=datetime.now(),
        data_sources={},
        raw_weather_payload={},
        weather_api_url="https://example.org",
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def _acne_profile() -> UserProfile:
    return UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )


def test_uv65_skin_colour_row_not_personalised_headline():
    store = get_evidence_store()
    uv65 = next(f for f in store.findings if f.id == "UV-65")
    bands = bucketize_environment(_env())
    assert not is_headline_eligible(
        uv65,
        profile=_acne_profile(),
        bands=bands,
        guest_mode=False,
        day_phase="morning",
    )


def test_personalised_pune_heat_prefers_env_today_over_education():
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
    )
    assert not any(f.id == "UV-65" for f in candidates)
    ranked = rank_findings(
        candidates,
        profile=profile,
        guest_mode=False,
        bands=bands,
    )
    headlines, _ = select_fire_budget(
        ranked,
        guest_mode=False,
        profile=profile,
        bands=bands,
    )
    assert headlines, "expected a hyper-local headline for acne + heat + UV"
    top = headlines[0]
    l1 = (top.alert_l1_personalised or "").lower()
    assert "skin colour varies" not in l1
    assert "varies hugely" not in l1
    assert top.user_filter, "personalised headline must be profile-tagged"


def test_guest_still_gets_broad_uv_rows():
    store = get_evidence_store()
    bands = bucketize_environment(_env())
    guest_matches = match_findings(
        store.findings,
        season=indian_season(),
        bands=bands,
        guest_mode=True,
        index=store.index,
    )
    assert guest_matches
    assert all(not f.user_filter for f in guest_matches)
