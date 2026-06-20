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
    def __init__(self, scans=None):
        self._scan = FakeCollection(scans)

    def __getitem__(self, name):
        if name == "hlhp_scan_log":
            return self._scan
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


def test_history_empty_returns_building_message():
    fake = FakeDb([])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=30))
    assert result.scan_count == 0
    assert result.message
    assert "Building your history" in result.message


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
        mp.setattr("app.hlhp.services.history_service._load_user_name", _fake_name)
        result = asyncio.run(assemble_history("u1", days=30))
    assert result.returner_banner is not None
    assert result.returner_banner.show is True
    assert result.returner_banner.days_away >= 14
