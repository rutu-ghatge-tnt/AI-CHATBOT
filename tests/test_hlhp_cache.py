"""Tests for HLHP cache backends."""

import asyncio
from unittest.mock import MagicMock, patch

from app.hlhp.utils.cache import get_cached, set_cached


def test_memory_cache_roundtrip():
    async def _run():
        with patch("app.hlhp.config.hl_settings.CACHE_BACKEND", "memory"):
            await set_cached("test:key", {"uv": 5}, 60)
            hit = await get_cached("test:key")
            assert hit == {"uv": 5}
            assert await get_cached("test:missing") is None

    asyncio.run(_run())


def test_mongo_cache_roundtrip():
    store: dict = {}

    async def fake_update_one(filter_doc, update_doc, upsert=False):
        store[filter_doc["key"]] = update_doc["$set"]

    async def fake_find_one(filter_doc):
        return store.get(filter_doc["key"])

    async def fake_create_index(*_args, **_kwargs):
        return None

    mock_col = MagicMock()
    mock_col.update_one = fake_update_one
    mock_col.find_one = fake_find_one
    mock_col.create_index = fake_create_index

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    async def _run():
        with patch("app.hlhp.config.hl_settings.CACHE_BACKEND", "mongo"):
            with patch("app.hlhp.utils.cache._mongo_index_ensured", True):
                with patch("app.hlhp.db.get_hlhp_db", return_value=mock_db):
                    await set_cached("hl:weather:19:72", {"uv_index": 8}, 900)
                    hit = await get_cached("hl:weather:19:72")
                    assert hit["uv_index"] == 8

    asyncio.run(_run())
