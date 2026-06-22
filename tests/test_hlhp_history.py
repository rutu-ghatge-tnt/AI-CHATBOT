"""History, catch-up, and consent logic tests (no live Mongo required)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.hlhp.services.history_service import assemble_catchup, assemble_history


async def _fake_name(_uid: str) -> str:
    return "Priya"


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        reverse = direction == -1
        field = key if isinstance(key, str) else key[0][0]
        asc = key[0][1] if isinstance(key, list) else direction
        reverse = asc == -1
        self._docs = sorted(
            self._docs,
            key=lambda d: d.get(field),
            reverse=reverse,
        )
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query, projection=None):
        user_id = query.get("user_id")
        since = query.get("scanned_at", {}).get("$gte")
        filtered = [d for d in self.docs if d.get("user_id") == user_id]
        if since is not None:
            filtered = [d for d in filtered if d["scanned_at"] >= since]
        return FakeCursor(filtered)

    async def find_one(self, query, sort=None, projection=None):
        user_id = query.get("user_id")
        matches = [d for d in self.docs if d.get("user_id") == user_id]
        if not matches:
            return None
        if sort and sort[0][0] == "scanned_at":
            reverse = sort[0][1] == -1
            matches = sorted(matches, key=lambda d: d["scanned_at"], reverse=reverse)
        return matches[0]


class FakeDb:
    def __init__(self, scans=None, feelings=None):
        self._scan = FakeCollection(scans)
        self._feelings = FakeCollection(feelings)

    def __getitem__(self, name):
        if name == "hlhp_scan_log":
            return self._scan
        if name == "hlhp_symptom_feeling_log":
            return self._feelings
        return FakeCollection()


def _scan(user_id: str, days_ago: int, sfi: int, mood: str, tags=None):
    return {
        "user_id": user_id,
        "scanned_at": datetime.now(timezone.utc) - timedelta(days=days_ago),
        "outdoor_ok_score": sfi,
        "mood_verdict": mood,
        "sudden_event_tags": tags or [],
        "city": "Mumbai",
        "uvi": 6.0,
        "temp_c": 32.0,
        "aqi": 80,
        "rh_pct": 60.0,
    }


def test_history_empty_returns_demo_logs():
    fake = FakeDb([])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=30))
    assert result.scan_count == 0
    assert result.is_demo is True
    assert len(result.daily_logs) == 7
    assert all(log.is_sample for log in result.daily_logs)
    assert result.message
    assert "Sample" in result.message or "sample" in result.message.lower()
    assert result.sfi_average is not None


def test_history_computes_sfi_average_and_trend():
    scans = [
        _scan("u1", 10, 60, "sebum_rush_day"),
        _scan("u1", 5, 70, "easy_day", tags=["heat_surge"]),
        _scan("u1", 1, 55, "sebum_rush_day"),
    ]
    fake = FakeDb(scans)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.history_service._load_user_name", _fake_name)
        result = asyncio.run(assemble_history("u1", days=30))
    assert result.scan_count == 3
    assert result.sfi_average == pytest.approx(61.7, abs=0.2)
    assert len(result.trend) == 3
    assert result.most_fired_mood is not None
    assert result.most_fired_mood.mood == "sebum_rush_day"
    assert result.most_fired_mood.days_count == 2
    assert len(result.sudden_events) >= 1


def test_catchup_returns_paragraphs():
    scans = [_scan("u1", 2, 62, "manageable_day")]
    fake = FakeDb(scans)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.history_service._load_user_name", _fake_name)
        result = asyncio.run(assemble_catchup("u1", days=30))
    assert len(result.paragraphs) >= 2
    assert "catch-up" in result.paragraphs[0].lower() or "Priya" in result.paragraphs[0]


def test_returner_banner_after_gap():
    scans = [
        _scan("u1", 20, 60, "easy_day"),
        _scan("u1", 1, 55, "sebum_rush_day"),
    ]
    fake = FakeDb(scans)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        mp.setattr("app.hlhp.services.history_service._load_user_name", _fake_name)
        result = asyncio.run(assemble_history("u1", days=30))
    assert result.returner_banner is not None
    assert result.returner_banner.show is True
    assert result.returner_banner.days_away >= 14


def test_history_daily_logs_merge_feelings():
    now = datetime.now(timezone.utc)
    scans = [_scan("u1", 1, 62, "manageable_day")]
    feelings = [
        {
            "user_id": "u1",
            "symptom_keyword": "oily",
            "selected": True,
            "recorded_at": now - timedelta(days=1),
        },
        {
            "user_id": "u1",
            "symptom_keyword": "shiny",
            "selected": True,
            "recorded_at": now - timedelta(days=1, hours=2),
        },
    ]
    fake = FakeDb(scans, feelings)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=30))
    real_logs = [log for log in result.daily_logs if log.logged]
    assert len(real_logs) >= 1
    feeling_log = next((log for log in real_logs if log.feelings), real_logs[0])
    assert "Oily" in feeling_log.feelings
    assert "Shiny" in feeling_log.feelings
    assert result.is_demo is True


def test_history_fully_real_when_enough_scans():
    scans = [_scan("u1", d, 55 + d, "easy_day") for d in range(7)]
    fake = FakeDb(scans)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=30))
    assert result.is_demo is False
    logged = [log for log in result.daily_logs if log.logged]
    assert all(not log.is_sample for log in logged)
    assert len(result.daily_logs) == 7


def test_history_fills_missing_calendar_days():
    scans = [_scan("u1", 0, 35, "easy_day"), _scan("u1", 3, 95, "easy_day")]
    fake = FakeDb(scans)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=30))
    assert len(result.daily_logs) == 7
    gaps = [log for log in result.daily_logs if not log.logged]
    assert len(gaps) == 5
    assert any("No scan logged" in log.mood_display for log in gaps)
