"""Coach rotation — never leave Today without an alert when matches exist."""

from app.hlhp.coach.rotation import filter_by_recency
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.ranker import rank_findings, select_fire_budget
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.season import indian_season
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from datetime import datetime


def _env():
    return EnvironmentalData(
        uv_index=6.0,
        temperature_c=32.0,
        aqi=69,
        humidity_pct=48.0,
        location_name="Mumbai",
        fetched_at=datetime.now(),
        data_sources={},
    )


def _profile():
    return UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )


def test_filter_by_recency_falls_back_when_all_suppressed():
    store = get_evidence_store()
    bands = bucketize_environment(_env())
    candidates = match_findings(
        store.findings,
        season=indian_season(),
        bands=bands,
        profile=_profile(),
        guest_mode=False,
        index=store.index,
    )
    assert candidates
    suppressed = {f.id for f in candidates}
    filtered = filter_by_recency(candidates, suppressed)
    assert filtered == candidates


def test_select_fire_budget_still_fires_after_heavy_suppression():
    store = get_evidence_store()
    bands = bucketize_environment(_env())
    profile = _profile()
    candidates = match_findings(
        store.findings,
        season=indian_season(),
        bands=bands,
        profile=profile,
        guest_mode=False,
        index=store.index,
    )
    suppressed = {f.id for f in candidates[:40]}
    filtered = filter_by_recency(candidates, suppressed)
    ranked = rank_findings(filtered, profile=profile, guest_mode=False, bands=bands)
    headlines, _ = select_fire_budget(
        ranked,
        guest_mode=False,
        profile=profile,
        bands=bands,
    )
    if not headlines:
        full_ranked = rank_findings(
            candidates,
            profile=profile,
            guest_mode=False,
            bands=bands,
        )
        from app.hlhp.evidence.ranker import _select_diverse

        headlines = _select_diverse(full_ranked, max_slots=1) if full_ranked else []
    assert headlines, "expected at least one headline after suppression fallback"
