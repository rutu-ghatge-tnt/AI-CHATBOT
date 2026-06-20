"""
HLHP v2 integration tests — spec scenarios + API contracts.

Run:
  python -m pytest tests/test_hlhp_integration.py -v
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from app.hlhp.coach.assembler import assemble_coach_wrap
from app.hlhp.coach.models import CoachContext
from app.hlhp.coach.streak_engine import compute_streak_after_tap, current_streak, streak_key
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.phase import resolve_day_phase
from app.hlhp.core.season import indian_season
from app.hlhp.evidence.gates import night_gate_blocks
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.ranker import select_fire_budget
from app.hlhp.evidence.selector import select_evidence_bundle
from app.hlhp.evidence.voice import validate_l1_voice
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    SkinConcern,
    SkinType,
    UserProfile,
)
from app.hlhp.models.scan import ScanRequest, SymptomTapRequest
from app.hlhp.services.action_tap_service import run_action_tap
from app.hlhp.services.outdoor_ok import compute_outdoor_ok
from app.hlhp.services.scan_service import run_scan, run_symptom_tap

IST = ZoneInfo("Asia/Kolkata")

IMPERATIVE_LEADERS = ("Apply", "Use", "Layer", "Wear", "Make", "Skip")
FORBIDDEN_INCI = ("vitamin c", "niacinamide", "retinol", "tretinoin")


def _env(**kwargs) -> EnvironmentalData:
    defaults = dict(
        uv_index=8.0,
        temperature_c=32.0,
        aqi=145,
        humidity_pct=72.0,
        location_name="Mumbai",
        fetched_at=datetime.now(timezone.utc),
        data_sources={"weather": "test"},
    )
    defaults.update(kwargs)
    return EnvironmentalData(**defaults)


def _profile(**kwargs) -> UserProfile:
    defaults = dict(
        user_id="test_priya",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.MELASMA, SkinConcern.PIGMENTATION],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
        hair_type=None,
        hair_concerns=[],
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


class TestEvidenceSnapshotIntegrity:
    def test_snapshot_scale_and_version(self):
        store = get_evidence_store()
        assert store.version >= 3
        assert len(store.findings) >= 1950
        assert len(store.findings) >= 1800
        assert len(store.nuggets) >= 18

    def test_findings_have_v2_engagement_on_p0_sample(self):
        store = get_evidence_store()
        p0_with_phase = [
            f
            for f in store.findings
            if f.priority == "P0" and f.time_of_day_phase and not f.internal_only
        ]
        assert len(p0_with_phase) > 100
        sample = p0_with_phase[0]
        assert sample.routine_action or sample.alert_l1_personalised


class TestSpecScenarioPriyaMumbaiMorning:
    """Phase 1 spec Test 1 — personalised Mumbai pre-monsoon morning."""

    def test_mumbai_morning_scan(self):
        req = ScanRequest(
            user_id="test_priya",
            city="Mumbai",
            local_time=datetime(2026, 5, 12, 8, 32, tzinfo=IST),
            raw_uvi=8.0,
            raw_aqi=145,
            raw_rh=72.0,
            raw_temp=31.0,
        )
        with patch("app.hlhp.services.scan_service.load_user_profile", return_value=_profile()):
            with patch("app.hlhp.services.scan_service.coach_voice_enabled", return_value=False):
                resp = asyncio.run(run_scan(req))
        assert resp.mode == "personalised"
        assert resp.env_snapshot.uvi_band == "very_high"
        assert resp.env_snapshot.season in {"summer", "pre_monsoon", "monsoon", "post_monsoon", "winter"}
        assert 0 <= resp.outdoor_ok_score <= 100
        assert len(resp.alerts) <= 3
        assert len(resp.candidate_alerts) <= 5
        if resp.alerts:
            self._assert_voice_discipline(resp.alerts[0].l1)

    def _assert_voice_discipline(self, text: str):
        lower = text.lower()
        for inci in FORBIDDEN_INCI:
            assert inci not in lower
        assert not any(text.startswith(w) for w in IMPERATIVE_LEADERS)


class TestSpecScenarioNightGate:
    def test_night_gate_suppresses_sunscreen_in_scan(self):
        req = ScanRequest(
            user_id="test_priya",
            city="Mumbai",
            local_time=datetime(2026, 5, 12, 23, 0, tzinfo=IST),
            raw_uvi=0.0,
            raw_aqi=145,
            raw_rh=72.0,
            raw_temp=28.0,
        )
        with patch("app.hlhp.services.scan_service.load_user_profile", return_value=_profile()):
            with patch("app.hlhp.services.scan_service.coach_voice_enabled", return_value=False):
                resp = asyncio.run(run_scan(req))
        for tile in resp.alerts + resp.candidate_alerts:
            assert "sunscreen" not in tile.l1.lower()
            assert "spf" not in tile.l1.lower()

    def test_night_gate_blocks_at_engine_level(self):
        store = get_evidence_store()
        blocked = [f for f in store.findings if night_gate_blocks(f, "off")]
        assert len(blocked) > 0


class TestSpecScenarioGuestMode:
    def test_guest_scan_has_nudge_and_no_personalised_only_filters(self):
        req = ScanRequest(
            user_id=None,
            city="Delhi",
            local_time=datetime(2026, 1, 15, 8, 0, tzinfo=IST),
            raw_uvi=3.0,
            raw_aqi=180,
            raw_rh=45.0,
            raw_temp=18.0,
        )
        resp = asyncio.run(run_scan(req))
        assert resp.mode == "guest"
        assert resp.profile_nudge is not None
        env = _env(uv_index=3.0, temperature_c=18.0, aqi=180, humidity_pct=45.0)
        bands = bucketize_environment(env)
        guest_matches = match_findings(
            get_evidence_store().findings,
            season=indian_season(),
            bands=bands,
            guest_mode=True,
            index=get_evidence_store().index,
        )
        assert all(not f.user_filter for f in guest_matches)


class TestOutdoorOkAndFireBudget:
    def test_outdoor_ok_in_manageable_range_for_mumbai_sample(self):
        """Mumbai pre-monsoon combo stress — score should be low, not 'manageable'."""
        env = _env(uv_index=8.0, aqi=145, temperature_c=31.0, humidity_pct=72.0)
        score, band_text = compute_outdoor_ok(env)
        assert 0 <= score <= 25
        assert "Hard" in band_text or "Plan around" in band_text

    def test_outdoor_ok_comfortable_day(self):
        env = _env(uv_index=2.0, aqi=45, temperature_c=24.0, humidity_pct=50.0)
        score, band_text = compute_outdoor_ok(env)
        assert score >= 80
        assert "Easy" in band_text or "Comfortable" in band_text

    def test_fire_budget_three_headlines_five_candidates(self):
        store = get_evidence_store()
        env = _env()
        bands = bucketize_environment(env)
        candidates = match_findings(
            store.findings,
            season=indian_season(),
            bands=bands,
            guest_mode=True,
            index=store.index,
        )
        from app.hlhp.evidence.ranker import rank_findings

        ranked = rank_findings(candidates, profile=None)
        headlines, swipe = select_fire_budget(ranked, headline_slots=3, candidate_slots=5)
        assert len(headlines) <= 3
        assert len(swipe) <= 5
        assert len(headlines) <= len(swipe)


class TestPhaseSelection:
    def test_evening_phase_uses_evening_l1_when_present(self):
        store = get_evidence_store()
        with_evening = [
            f
            for f in store.findings
            if f.alert_l1_evening_personalised and f.time_of_day_phase in {"evening_recovery", "both_phases"}
        ]
        assert with_evening, "workbook should have evening L1 rows"
        f = with_evening[0]
        morning = f.pick_l1(guest_mode=False, day_phase="morning")
        evening = f.pick_l1(guest_mode=False, day_phase="evening")
        if f.alert_l1_evening_personalised:
            assert evening == f.alert_l1_evening_personalised or evening != morning

    def test_am_pm_boundary(self):
        assert resolve_day_phase(datetime(2026, 6, 18, 8, 0, tzinfo=IST)) == "morning"
        assert resolve_day_phase(datetime(2026, 6, 18, 20, 0, tzinfo=IST)) == "evening"


class TestSymptomTap:
    def test_symptom_tap_returns_structure(self):
        req = SymptomTapRequest(
            user_id=None,
            symptom_keyword="oily",
            city="Mumbai",
            local_time=datetime(2026, 6, 18, 14, 0, tzinfo=IST),
            raw_uvi=8.0,
            raw_aqi=120,
            raw_rh=70.0,
            raw_temp=32.0,
        )
        resp = asyncio.run(run_symptom_tap(req))
        assert resp.headline
        assert resp.decode_text
        assert resp.tip


class TestCoachContract:
    def test_coach_never_fakes_effort_for_new_user(self):
        ctx = CoachContext(user_id="new", name="Aarav", recent_actions=[], streaks={})
        store = get_evidence_store()
        finding = next(f for f in store.findings if f.routine_action == "apply_sunscreen" and f.is_surfaced_to_client())
        wrap = assemble_coach_wrap(
            finding,
            ctx,
            uvi_band="very_high",
            day_phase="morning",
            mood_verdict="easy_day",
            forecast=None,
            env_uvi=8.0,
            env_aqi=100,
            local_time=datetime(2026, 6, 18, 9, 0, tzinfo=IST),
        )
        assert wrap.effort_recognition is None

    def test_streak_semantics_spec(self):
        key = streak_key("very_high", "apply_sunscreen")
        d0 = datetime(2026, 6, 1, 8, tzinfo=timezone.utc)
        d2 = datetime(2026, 6, 3, 8, tzinfo=timezone.utc)
        d5 = datetime(2026, 6, 6, 8, tzinfo=timezone.utc)
        r1 = compute_streak_after_tap(None, streak_key_val=key, today=d0.date(), tapped_at=d0)
        assert current_streak(r1, d0.date()) == 1
        r2 = compute_streak_after_tap(r1, streak_key_val=key, today=d2.date(), tapped_at=d2)
        assert current_streak(r2, d2.date()) == 2
        r3 = compute_streak_after_tap(r2, streak_key_val=key, today=d5.date(), tapped_at=d5)
        assert current_streak(r3, d5.date()) == 1


class TestActionTapWithMockMongo:
    def test_action_tap_increments_streak(self):
        store_data: dict = {}

        async def fake_update_one(filter_doc, update_doc, upsert=False):
            k = (filter_doc["user_id"], filter_doc["streak_key"])
            existing = store_data.get(k, {})
            existing.update(update_doc.get("$set", {}))
            store_data[k] = existing

        async def fake_find_one(filter_doc):
            k = (filter_doc["user_id"], filter_doc.get("streak_key"))
            return store_data.get(k)

        async def fake_insert_one(doc):
            store_data.setdefault("actions", []).append(doc)

        mock_streaks = MagicMock()
        mock_streaks.update_one = fake_update_one
        mock_streaks.find_one = fake_find_one

        mock_actions = MagicMock()
        mock_actions.insert_one = fake_insert_one

        class FakeDb:
            def __getitem__(self, name: str):
                if name == "hlhp_streak_counters":
                    return mock_streaks
                if name == "hlhp_action_log":
                    return mock_actions
                return MagicMock()

        from app.hlhp.coach.models import ActionTapRequest

        req = ActionTapRequest(
            user_id="u_test",
            routine_action="apply_sunscreen",
            current_time=datetime(2026, 6, 18, 9, 0, tzinfo=IST),
            location_city="Mumbai",
            raw_uvi=8.0,
            raw_aqi=120,
            raw_rh=55.0,
            raw_temp=30.0,
        )

        with patch("app.hlhp.coach.state_store.hl_db", FakeDb()):
            resp = asyncio.run(run_action_tap(req))
        assert resp.streak >= 1
        assert resp.longest_ever >= 1


class TestScanWithCoachMocked:
    def test_personalised_scan_attaches_coach_wrap_when_enabled(self):
        req = ScanRequest(
            user_id="u_coach_test",
            city="Mumbai",
            local_time=datetime(2026, 6, 18, 9, 0, tzinfo=IST),
            raw_uvi=8.0,
            raw_aqi=145,
            raw_rh=72.0,
            raw_temp=31.0,
        )
        mock_ctx = CoachContext(user_id="u_coach_test", name="Priya", recent_actions=[], streaks={})

        with patch("app.hlhp.services.scan_service.coach_voice_enabled", return_value=True):
            with patch("app.hlhp.services.scan_service.load_user_profile", return_value=_profile()):
                with patch("app.hlhp.services.scan_service.load_coach_context", return_value=mock_ctx):
                    with patch("app.hlhp.services.scan_service.record_surfaced_rules", return_value=None):
                        with patch("app.hlhp.services.scan_service.record_nugget_shown", return_value=None):
                            resp = asyncio.run(run_scan(req))

        assert resp.mode == "personalised"
        if resp.alerts:
            assert resp.alerts[0].coach_wrap is not None
            assert resp.alerts[0].coach_wrap.greeting
            assert resp.alerts[0].coach_wrap.effort_recognition is None


class TestBuildGatesSample:
    def test_voice_violations_below_threshold(self):
        """Build should not have hundreds of voice failures — spot-check count."""
        store = get_evidence_store()
        snap = json.loads(
            Path("app/hlhp/data/evidence_snapshot_v1.json").read_text(encoding="utf-8")
        )
        issues = validate_l1_voice(snap["findings"], store.glossary)
        assert len(issues) < 100, f"too many voice issues: {len(issues)}"


class TestAPIHealthEndpoint:
    def test_health_via_asgi(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/hlhp/health")
                assert r.status_code == 200
                body = r.json()
                assert body["ok"] is True
                assert body["rule_count"] >= 1950
                assert body.get("workbook_version") == "1.0"
                assert body.get("composition_row_count", 0) > 0

        asyncio.run(_call())

    def test_scan_guest_via_asgi(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/api/hlhp/scan",
                    json={
                        "user_id": None,
                        "city": "Mumbai",
                        "local_time": "2026-05-12T08:32:00+05:30",
                        "raw_uvi": 8.0,
                        "raw_aqi": 145,
                        "raw_rh": 72.0,
                        "raw_temp": 31.0,
                    },
                )
                assert r.status_code == 200
                data = r.json()
                assert data["mode"] == "guest"
                assert "outdoor_ok_score" in data
                assert "mood_headline" in data
                assert "lane_state_ctas" in data
                assert data.get("workbook_version") == "1.0"

        asyncio.run(_call())

    def test_explore_lane_via_asgi(self):
        try:
            from httpx import ASGITransport, AsyncClient
        except ImportError:
            pytest.skip("httpx ASGITransport not available")

        async def _call():
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.get("/api/hlhp/explore", params={"city": "Mumbai"})
                assert r.status_code == 200
                body = r.json()
                assert body["city"] == "Mumbai"
                assert "event_guides" in body
                assert body.get("snapshot_version") == "1.0"

        asyncio.run(_call())
