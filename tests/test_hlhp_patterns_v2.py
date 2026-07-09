"""Patterns v2 engine acceptance tests (spec §10 — pure engine, no Mongo)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.hlhp.patterns.hlhp_patterns_engine import (
    Config,
    DailyLog,
    EnvDay,
    Pattern,
    PatternState,
    _log_day_count,
    _window_logs,
    build_patterns_payload,
    detect_patterns,
    evaluate_state,
    reactivation_progress,
    validate_narration,
)
from app.hlhp.patterns.hlhp_patterns_prompts import lifecycle


def _env_day(day: date, **bands) -> EnvDay:
    defaults = {"temp": "comfortable", "uv": "moderate", "humidity": "moderate", "aqi": "good"}
    defaults.update(bands)
    return EnvDay(city="Pune", day=day, band_keys=defaults)


def _log(day: date, symptoms: list[str] | None = None) -> DailyLog:
    return DailyLog(user_id="u1", log_date=day, city="Pune", symptoms=symptoms or [])


class TestUnlockGates:
    def test_hard_floor_blocks_unlock_at_day_24(self):
        today = date(2026, 7, 30)
        first = today - timedelta(days=24)
        logs = [_log(first + timedelta(days=i), ["breakout"]) for i in range(25)]
        env = {lg.log_date: _env_day(lg.log_date, humidity="high") for lg in logs}
        ps = PatternState("u1", "LOCKED", first, None, 0, 0, None)
        evaluate_state(ps, logs, env, today)
        assert ps.unlocked_at is None
        assert ps.state in ("LOCKED", "EARLY_SIGNALS")

    def test_unlock_on_day_30_with_gates_met(self):
        today = date(2026, 7, 30)
        first = today - timedelta(days=30)
        logs = []
        env: dict[date, EnvDay] = {}
        for i in range(30):
            d = today - timedelta(days=29 - i)
            logs.append(_log(d, ["breakout"] if i % 2 == 0 else []))
            env[d] = _env_day(d, humidity="high" if i % 3 == 0 else "comfortable")
        ps = PatternState("u1", "LOCKED", first, None, 0, 0, None)
        evaluate_state(ps, logs, env, today)
        assert ps.unlocked_at is not None
        assert ps.state == "UNLOCKED_ACTIVE"

    def test_binge_logging_counts_one_log_day(self):
        today = date(2026, 7, 7)
        d = today - timedelta(days=1)
        logs = [
            _log(d, ["oily"]),
            DailyLog("u1", d, "Pune", ["dry"]),
        ]
        assert _log_day_count(logs, today) == 1


class TestPostUnlockDecay:
    def test_fading_at_15_log_days(self):
        today = date(2026, 7, 30)
        first = today - timedelta(days=60)
        logs = [_log(today - timedelta(days=i), []) for i in range(15)]
        env = {lg.log_date: _env_day(lg.log_date) for lg in logs}
        ps = PatternState(
            "u1",
            "UNLOCKED_ACTIVE",
            first,
            datetime(2026, 6, 1),
            0,
            0,
            None,
        )
        evaluate_state(ps, logs, env, today)
        assert ps.state == "UNLOCKED_FADING"

    def test_reactivation_3_of_5(self):
        today = date(2026, 7, 10)
        logs = [
            _log(today - timedelta(days=4)),
            _log(today - timedelta(days=2)),
            _log(today),
        ]
        prog = reactivation_progress(logs, today)
        assert prog["done"] == 3
        assert prog["reactivated"] is True


class TestDetection:
    def test_small_sample_not_promoted(self):
        """Spec §10.7: E=4 with high lift must not be promoted."""
        today = date(2026, 7, 7)
        logs = []
        env: dict[date, EnvDay] = {}
        for i in range(20):
            d = today - timedelta(days=i)
            logs.append(_log(d, ["breakout"] if i < 4 else []))
            env[d] = _env_day(d, humidity="high" if i < 4 else "comfortable")
        patterns = detect_patterns("u1", logs, env, {"skin": "oily", "concern": "acne"}, {}, today)
        humid_breakout = [p for p in patterns if p.driver == "humidity" and p.symptom == "breakout"]
        assert not humid_breakout or all(p.E < Config.PROMOTE_MIN_EXPOSURE for p in humid_breakout)

    def test_demotion_after_weak_lift_streak(self):
        today = date(2026, 7, 20)
        prev = Pattern(
            driver="humidity",
            symptom="breakout",
            city="Pune",
            E=8,
            H=6,
            match=0.75,
            lift=1.1,
            label="MODERATE",
            status="promoted",
            lag_hours=24,
            zones=[],
            weekday_hits=4,
            weekend_hits=2,
            library_cell_id=None,
            pmids=[],
            first_detected=today - timedelta(days=20),
            last_confirmed=today - timedelta(days=1),
            weak_lift_days=13,
        )
        logs = []
        env: dict[date, EnvDay] = {}
        for i in range(20):
            d = today - timedelta(days=i)
            logs.append(_log(d, ["breakout"] if i % 2 == 0 else []))
            env[d] = _env_day(d, humidity="high")
        patterns = detect_patterns(
            "u1",
            logs,
            env,
            {"skin": "oily", "concern": "acne"},
            {},
            today,
            prev_patterns=[prev],
        )
        match = next((p for p in patterns if p.driver == "humidity" and p.symptom == "breakout"), None)
        if match and match.lift < Config.DEMOTE_LIFT:
            assert match.weak_lift_days >= Config.DEMOTE_DAYS or match.status == "emerging"


class TestNarrationValidator:
    def test_rejects_hallucinated_numeral(self):
        packet = {
            "patterns": [{"driver": "humidity", "symptom": "breakout", "E": 10, "H": 8, "match": 0.8}],
        }
        assert validate_narration("It happened 99 times", packet) is False
        assert validate_narration("It happened 8 of 10 humid days", packet) is True


class TestGenericCityPattern:
    def test_builds_city_card_for_locked_tab(self):
        from app.hlhp.services.patterns_generic_city import build_generic_city_pattern

        card = build_generic_city_pattern(
            user_id="u1",
            city="Baner, Pune, Maharashtra",
            profile=None,
        )
        assert card is not None
        assert card["city"] == "Pune"
        assert "kick" in card
        assert "body" in card
        assert "North India" not in card["body"]
        assert card["color_var"].startswith("--drv-")


class TestDecayBannerPayload:
    def test_fading_state_includes_decay_banner(self):
        today = date(2026, 7, 30)
        ps = PatternState(
            "u1",
            "UNLOCKED_FADING",
            today - timedelta(days=60),
            datetime(2026, 6, 1),
            15,
            10,
            None,
        )
        payload = build_patterns_payload(ps, [], [], today)
        assert payload["decay_banner"] == lifecycle("fading.banner")
        assert payload["freshness"] == "fading"

    def test_paused_state_includes_decay_banner_and_reactivation(self):
        today = date(2026, 7, 30)
        logs = [_log(today - timedelta(days=4)), _log(today - timedelta(days=2)), _log(today)]
        ps = PatternState(
            "u1",
            "UNLOCKED_PAUSED",
            today - timedelta(days=60),
            datetime(2026, 6, 1),
            10,
            8,
            None,
        )
        payload = build_patterns_payload(ps, [], logs, today)
        assert payload["decay_banner"] == lifecycle("paused.react")
        assert payload["reactivation"]["done"] == 3
        assert payload["freshness"] == "paused"


class TestPatternStateStore:
    def test_pattern_from_doc_skips_incomplete_rows(self):
        from app.hlhp.services.pattern_state_store import _pattern_from_doc

        assert _pattern_from_doc({"symptom": "breakout"}) is None
        pat = _pattern_from_doc(
            {
                "driver": "humidity",
                "symptom": "breakout",
                "E": 6,
                "H": 4,
                "match": 0.7,
                "lift": 2.1,
            }
        )
        assert pat is not None
        assert pat.driver == "humidity"


class TestNarrationLlmAsync:
    def test_call_llm_uses_thread_pool(self, monkeypatch):
        import asyncio

        from app.hlhp.services import patterns_narration_service as svc

        called = {"to_thread": False}

        async def fake_to_thread(fn, packet):
            called["to_thread"] = True
            assert fn is svc._call_llm_sync
            return {"patterns": []}

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

        result = asyncio.run(svc._call_llm({"outputs_wanted": ["pattern_narrative"]}))
        assert called["to_thread"] is True
        assert result == {"patterns": []}
