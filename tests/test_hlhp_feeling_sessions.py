"""Feeling log sessions — cooldown gate and session-level pattern mining."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.hlhp.services.engagement_service import run_user_log
from app.hlhp.services.log_event_store import (
    FEELING_LOG_COOLDOWN_HOURS,
    FeelingLogCooldownError,
    assert_feeling_log_allowed,
    feeling_log_cooldown_remaining,
    next_feeling_log_at,
)
from app.hlhp.services.patterns_service import (
    DriverRule,
    MIN_LOGS_TO_MINE,
    PATTERNS_UNLOCK_DAYS,
    SessionRecord,
    _evaluate,
    _mining_gate_copy,
    _pattern_unlock_copy,
    _session_from_event,
    _sessions_from_events,
)


def test_cooldown_blocks_within_five_hours():
    last = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)
    attempt = last + timedelta(hours=3)
    remaining = feeling_log_cooldown_remaining(last, attempt)
    assert remaining is not None
    assert remaining == 2 * 3600
    with pytest.raises(FeelingLogCooldownError) as exc:
        assert_feeling_log_allowed(last, attempt)
    assert exc.value.retry_after_seconds == 2 * 3600
    assert exc.value.next_log_at == next_feeling_log_at(last)


def test_cooldown_allows_after_five_hours():
    last = datetime(2026, 7, 6, 8, 0, tzinfo=timezone.utc)
    attempt = last + timedelta(hours=5)
    assert feeling_log_cooldown_remaining(last, attempt) is None
    assert_feeling_log_allowed(last, attempt)


def test_session_from_event_preserves_point_in_time_env():
    when = datetime(2026, 7, 6, 20, 30, tzinfo=timezone.utc)
    doc = {
        "session_id": "s1",
        "ts": when,
        "date": "2026-07-06",
        "symptoms": ["dry"],
        "sfi": 42,
        "uvi": 2.0,
        "temp_c": 28.0,
        "aqi": 55,
        "rh_pct": 40.0,
        "sudden_event_tags": [],
    }
    session = _session_from_event(doc)
    assert session is not None
    assert session.sfi == 42
    assert session.rh_pct == 40.0
    assert session.feelings == {"dry"}


def test_pattern_eval_uses_session_snapshot_not_day_average():
    humid_rule = DriverRule("humidity_high", "high humidity", lambda s: s.rh_pct is not None and s.rh_pct > 75)
    sessions = _sessions_from_events(
        [
            {
                "session_id": "morning",
                "ts": datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
                "date": "2026-07-01",
                "symptoms": ["oily"],
                "sfi": 72,
                "rh_pct": 82.0,
                "uvi": 4,
                "temp_c": 30,
                "aqi": 60,
            },
            {
                "session_id": "evening",
                "ts": datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc),
                "date": "2026-07-01",
                "symptoms": ["dry"],
                "sfi": 48,
                "rh_pct": 45.0,
                "uvi": 0,
                "temp_c": 26,
                "aqi": 60,
            },
            {
                "session_id": "d2",
                "ts": datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
                "date": "2026-07-02",
                "symptoms": ["oily"],
                "sfi": 70,
                "rh_pct": 80.0,
                "uvi": 5,
                "temp_c": 31,
                "aqi": 55,
            },
            {
                "session_id": "d3",
                "ts": datetime(2026, 7, 3, 9, 0, tzinfo=timezone.utc),
                "date": "2026-07-03",
                "symptoms": ["oily"],
                "sfi": 68,
                "rh_pct": 78.0,
                "uvi": 6,
                "temp_c": 30,
                "aqi": 50,
            },
        ]
    )
    hit = _evaluate(sessions, "oily", humid_rule)
    assert hit is not None
    assert hit["n_symptom"] == 3
    assert hit["n_both"] == 3


class FakeLogEvents:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, sort=None):
        user_id = query.get("user_id")
        filtered = [d for d in self.docs if d.get("user_id") == user_id]
        if not filtered:
            return None
        field, direction = sort[0]
        reverse = direction == -1
        filtered.sort(key=lambda d: d.get(field), reverse=reverse)
        return filtered[0]

    def find(self, query):
        return FakeCursor(self.docs, query)


class FakeCursor:
    def __init__(self, docs, query):
        self._docs = [d for d in docs if d.get("user_id") == query.get("user_id")]

    def sort(self, field, direction):
        reverse = direction == -1
        self._docs.sort(key=lambda d: d.get(field), reverse=reverse)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc

    def insert_one(self, doc):
        self._docs.append(doc)
        return None


class FakeHlDb:
    def __init__(self, log_events=None):
        self._log_events = FakeLogEvents(log_events)

    def __getitem__(self, name):
        if name == "hlhp_user_log_events":
            return self._log_events
        raise KeyError(name)


def test_run_user_log_rejects_second_commit_within_cooldown():
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(hours=2)
    fake_db = FakeHlDb(
        [
            {
                "user_id": "u1",
                "ts": earlier,
                "date": earlier.date().isoformat(),
                "symptoms": ["oily"],
            }
        ]
    )
    body = type(
        "Body",
        (),
        {
            "user_id": "u1",
            "symptoms": ["dry"],
            "areas": [],
            "local_time": now,
            "routine_action": "Maintain",
            "rule_id": None,
            "location_city": "Pune",
            "latitude": None,
            "longitude": None,
            "raw_uvi": 5.0,
            "raw_aqi": 60,
            "raw_rh": 50.0,
            "raw_temp": 28.0,
            "outdoor_ok_score": 60,
            "mood_verdict": None,
            "sudden_event_tags": None,
        },
    )()
    async def _fake_profile(_uid):
        return object()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.log_event_store.hl_db", fake_db)
        mp.setattr("app.hlhp.services.engagement_service.load_user_profile", _fake_profile)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(run_user_log(body))
    assert exc.value.status_code == 429
    detail = exc.value.detail
    assert detail["code"] == "feeling_log_cooldown"
    assert detail["cooldown_hours"] == FEELING_LOG_COOLDOWN_HOURS


def test_pattern_unlock_uses_journey_day_not_log_count():
    ready, needed, headline, detail = _pattern_unlock_copy(6)
    assert ready is False
    assert needed == PATTERNS_UNLOCK_DAYS - 6
    assert f"after {PATTERNS_UNLOCK_DAYS} days on your track" in headline
    assert "day 6 of your track" in detail
    assert "24 more days" in detail
    assert "32" not in detail

    ready30, needed30, _, _ = _pattern_unlock_copy(PATTERNS_UNLOCK_DAYS)
    assert ready30 is True
    assert needed30 == 0


def test_pattern_mining_requires_enough_feeling_log_days():
    can_mine, needed, message = _mining_gate_copy(6)
    assert can_mine is False
    assert needed == MIN_LOGS_TO_MINE - 6
    assert "25 days" in message
    assert "6 of 25" in message

    can_mine25, needed25, _ = _mining_gate_copy(MIN_LOGS_TO_MINE)
    assert can_mine25 is True
    assert needed25 == 0
