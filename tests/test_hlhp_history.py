"""History, catch-up, and daily log tests (no live Mongo required)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.hlhp.services.daily_log_store import RETENTION_DAYS, upsert_from_scan
from app.hlhp.services.history_service import assemble_catchup, assemble_history


async def _fake_name(_uid: str) -> str:
    return "Priya"


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        if isinstance(key, list):
            field, asc = key[0]
            reverse = asc == -1
        else:
            field = key
            reverse = direction == -1
        self._docs = sorted(self._docs, key=lambda d: d.get(field), reverse=reverse)
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
        filtered = list(self.docs)
        user_id = query.get("user_id")
        if user_id is not None:
            filtered = [d for d in filtered if d.get("user_id") == user_id]
        since = query.get("scanned_at", {}).get("$gte")
        if since is not None:
            filtered = [d for d in filtered if d.get("scanned_at") >= since]
        date_gte = query.get("date", {}).get("$gte")
        if date_gte is not None:
            filtered = [d for d in filtered if d.get("date") >= date_gte]
        date_lt = query.get("date", {}).get("$lt")
        if date_lt is not None:
            filtered = [d for d in filtered if d.get("date") < date_lt]
        return FakeCursor(filtered)

    async def find_one(self, query, sort=None, projection=None):
        user_id = query.get("user_id")
        date_key = query.get("date")
        matches = [d for d in self.docs if d.get("user_id") == user_id]
        if date_key is not None:
            matches = [d for d in matches if d.get("date") == date_key]
        if not matches:
            return None
        if sort and sort[0][0] == "scanned_at":
            reverse = sort[0][1] == -1
            matches = sorted(matches, key=lambda d: d["scanned_at"], reverse=reverse)
        return matches[0]

    async def update_one(self, query, update, upsert=False):
        user_id = query.get("user_id")
        date_key = query.get("date")
        existing = next(
            (d for d in self.docs if d.get("user_id") == user_id and d.get("date") == date_key),
            None,
        )
        payload = update.get("$set", {})
        if existing:
            existing.update(payload)
        elif upsert:
            self.docs.append({**query, **payload})

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def delete_many(self, query):
        user_id = query.get("user_id")
        date_lt = query.get("date", {}).get("$lt")
        keep = []
        for doc in self.docs:
            if doc.get("user_id") != user_id:
                keep.append(doc)
                continue
            if date_lt is not None and doc.get("date", "") < date_lt:
                continue
            keep.append(doc)
        self.docs = keep

    async def create_index(self, *args, **kwargs):
        return None


class FakeDb:
    def __init__(self, scans=None, feelings=None, daily_logs=None):
        self._scan = FakeCollection(scans)
        self._feelings = FakeCollection(feelings)
        self._daily = FakeCollection(daily_logs)

    def __getitem__(self, name):
        if name == "hlhp_scan_log":
            return self._scan
        if name == "hlhp_symptom_feeling_log":
            return self._feelings
        if name == "hlhp_daily_log":
            return self._daily
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


def _daily(user_id: str, days_ago: int, avg: float, mood: str, tags=None, scan_count=1):
    day = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return {
        "user_id": user_id,
        "date": day,
        "outdoor_score_avg": avg,
        "scan_count": scan_count,
        "mood_verdict": mood,
        "sudden_event_tags": tags or [],
        "sudden_event": bool(tags),
        "uvi": 6.0,
        "temp_c": 32.0,
        "aqi": 80,
        "rh_pct": 60.0,
        "city": "Mumbai",
        "updated_at": datetime.now(timezone.utc),
    }


def test_history_empty_returns_no_demo():
    fake = FakeDb([], [], [])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=15))
    assert result.scan_count == 0
    assert result.is_demo is False
    assert result.daily_logs == []
    assert result.sfi_average is None
    assert result.show_tracking_prompt is True
    assert result.tracking_prompt


def test_history_reads_saved_daily_logs_only():
    daily = [
        _daily("u1", 2, 62.0, "manageable_day"),
        _daily("u1", 0, 55.0, "easy_day"),
    ]
    fake = FakeDb([], [], daily)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=15))
    assert len(result.daily_logs) == 2
    assert all(not log.is_sample for log in result.daily_logs)
    assert result.sfi_average == pytest.approx(58.5, abs=0.1)
    assert result.is_demo is False


def test_history_backfills_daily_logs_from_scans_when_missing():
    scans = [
        _scan("u1", 1, 62, "manageable_day"),
        _scan("u1", 3, 70, "easy_day", tags=["heat_surge"]),
    ]
    fake = FakeDb(scans, [], [])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=15))
    assert len(result.daily_logs) == 2
    assert len(fake._daily.docs) == 2


def test_history_daily_logs_without_mood_verdict():
    daily = [
        {
            "user_id": "u1",
            "date": (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat(),
            "outdoor_score_avg": 55.0,
            "user_logged": True,
        }
    ]
    fake = FakeDb([], [], daily)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=15))
    assert len(result.daily_logs) == 1
    assert result.daily_logs[0].mood_display == ""


def test_history_daily_logs_merge_feelings():
    now = datetime.now(timezone.utc)
    daily = [_daily("u1", 1, 62.0, "manageable_day")]
    feelings = [
        {
            "user_id": "u1",
            "symptom_keyword": "oily",
            "selected": True,
            "recorded_at": now - timedelta(days=1),
        },
    ]
    fake = FakeDb([], feelings, daily)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=15))
    assert result.daily_logs[0].feelings == ["Oily"]


def test_history_daily_average_when_multiple_scans_same_day():
    noon = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    scans = [
        {**_scan("u1", 0, 40, "easy_day"), "scanned_at": noon - timedelta(hours=4)},
        {**_scan("u1", 0, 60, "easy_day"), "scanned_at": noon + timedelta(hours=2)},
    ]
    fake = FakeDb(scans, [], [])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        result = asyncio.run(assemble_history("u1", days=15))
    assert len(result.daily_logs) == 1
    assert result.daily_logs[0].outdoor_score == 50
    assert result.sfi_average == 50.0


def test_daily_log_upsert_averages_multiple_scans():
    fake = FakeDb()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        when = datetime.now(timezone.utc)
        asyncio.run(
            upsert_from_scan(
                user_id="u1",
                scanned_at=when,
                outdoor_ok_score=40,
                mood_verdict="easy_day",
                sudden_event_tags=[],
                uvi=3.0,
                temp_c=28.0,
                aqi=50,
                rh_pct=60.0,
                city="Pune",
            )
        )
        asyncio.run(
            upsert_from_scan(
                user_id="u1",
                scanned_at=when + timedelta(hours=3),
                outdoor_ok_score=60,
                mood_verdict="easy_day",
                sudden_event_tags=[],
                uvi=5.0,
                temp_c=30.0,
                aqi=50,
                rh_pct=55.0,
                city="Pune",
            )
        )
    assert len(fake._daily.docs) == 1
    assert fake._daily.docs[0]["outdoor_score_avg"] == 50.0
    assert fake._daily.docs[0]["scan_count"] == 2


def test_catchup_returns_paragraphs():
    daily = [_daily("u1", 2, 62.0, "manageable_day")]
    fake = FakeDb([], [], daily)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.history_service._load_user_name", _fake_name)
        result = asyncio.run(assemble_catchup("u1", days=15))
    assert len(result.paragraphs) >= 2


def test_returner_banner_after_gap():
    scans = [
        _scan("u1", 20, 60, "easy_day"),
        _scan("u1", 1, 55, "sebum_rush_day"),
    ]
    daily = [_daily("u1", 1, 55.0, "sebum_rush_day")]
    fake = FakeDb(scans, [], daily)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.services.scan_log_store.hl_db", fake)
        mp.setattr("app.hlhp.services.daily_log_store.hl_db", fake)
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        mp.setattr("app.hlhp.services.history_service._load_user_name", _fake_name)
        result = asyncio.run(assemble_history("u1", days=15))
    assert result.returner_banner is not None
    assert result.returner_banner.show is True


def test_history_caps_at_15_days():
    assert RETENTION_DAYS == 15
