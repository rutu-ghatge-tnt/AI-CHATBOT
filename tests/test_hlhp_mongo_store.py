"""HLHP Mongo store error and index setup tests."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from app.hlhp.api.store_http import http_503_for_store_error
from app.hlhp.db_errors import HlhpStoreError, fail_write


def test_fail_write_raises_hlhp_store_error():
    with pytest.raises(HlhpStoreError) as exc_info:
        fail_write("hlhp_user_log_events", "insert", RuntimeError("disk full"))
    err = exc_info.value
    assert err.collection == "hlhp_user_log_events"
    assert err.operation == "insert"
    assert isinstance(err.cause, RuntimeError)


def test_http_503_for_store_error():
    exc = HlhpStoreError(
        collection="hlhp_daily_log",
        operation="upsert_user_log_day",
        cause=RuntimeError("timeout"),
    )
    with pytest.raises(HTTPException) as raised:
        http_503_for_store_error(exc)
    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "store_write_failed"


class _FakeCol:
    def __init__(self):
        self.index_calls = 0

    async def create_index(self, *args, **kwargs):
        self.index_calls += 1


class _FakeDb:
    def __init__(self):
        self._cols: dict[str, _FakeCol] = {}

    def __getitem__(self, name: str) -> _FakeCol:
        return self._cols.setdefault(name, _FakeCol())


def test_ensure_hlhp_indexes_runs_once(monkeypatch):
    from app.hlhp import mongo_setup

    mongo_setup._indexes_ensured = False
    fake = _FakeDb()
    monkeypatch.setattr(mongo_setup, "hl_db", fake)

    asyncio.run(mongo_setup.ensure_hlhp_indexes())
    assert mongo_setup._indexes_ensured is True
    first_total = sum(c.index_calls for c in fake._cols.values())
    assert first_total > 0

    asyncio.run(mongo_setup.ensure_hlhp_indexes())
    second_total = sum(c.index_calls for c in fake._cols.values())
    assert second_total == first_total
