"""Symptom feeling toggle tests — deselect must win over prior select."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.hlhp.coach.state_store import fetch_selected_symptoms


class FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        reverse = direction == -1
        field = key if isinstance(key, str) else key
        self._docs = sorted(self._docs, key=lambda d: d.get(field), reverse=reverse)
        return self

    async def __aiter__(self):
        for doc in self._docs:
            yield doc


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query, projection=None):
        user_id = query.get("user_id")
        since = query.get("recorded_at", {}).get("$gte")
        filtered = [d for d in self.docs if d.get("user_id") == user_id]
        if since is not None:
            filtered = [d for d in filtered if d["recorded_at"] >= since]
        return FakeCursor(filtered)


class FakeDb:
    def __init__(self, feelings=None):
        self._feelings = FakeCollection(feelings)

    def __getitem__(self, name):
        if name == "hlhp_symptom_feeling_log":
            return self._feelings
        return FakeCollection()


def test_deselect_removes_keyword_from_active_set():
    now = datetime.now(timezone.utc)
    feelings = [
        {
            "user_id": "u1",
            "symptom_keyword": "oily",
            "selected": True,
            "recorded_at": now - timedelta(hours=2),
        },
        {
            "user_id": "u1",
            "symptom_keyword": "oily",
            "selected": False,
            "recorded_at": now - timedelta(hours=1),
        },
        {
            "user_id": "u1",
            "symptom_keyword": "shiny",
            "selected": True,
            "recorded_at": now - timedelta(minutes=30),
        },
    ]
    fake = FakeDb(feelings)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        active = asyncio.run(fetch_selected_symptoms("u1"))
    assert active == {"shiny"}


def test_reselect_after_deselect():
    now = datetime.now(timezone.utc)
    feelings = [
        {
            "user_id": "u1",
            "symptom_keyword": "tight",
            "selected": True,
            "recorded_at": now - timedelta(hours=3),
        },
        {
            "user_id": "u1",
            "symptom_keyword": "tight",
            "selected": False,
            "recorded_at": now - timedelta(hours=2),
        },
        {
            "user_id": "u1",
            "symptom_keyword": "tight",
            "selected": True,
            "recorded_at": now - timedelta(hours=1),
        },
    ]
    fake = FakeDb(feelings)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.hlhp.coach.state_store.hl_db", fake)
        active = asyncio.run(fetch_selected_symptoms("u1"))
    assert active == {"tight"}
