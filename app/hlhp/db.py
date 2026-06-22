"""MongoDB access for HLHP profile and state."""

from __future__ import annotations

import os
from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


@lru_cache
def _client() -> AsyncIOMotorClient:
    uri = os.getenv("MONGO_URI") or os.getenv("PRODUCTION_MONGO_URI", "")
    if not uri:
        raise RuntimeError("MONGO_URI is not configured")
    return AsyncIOMotorClient(
        uri,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=20000,
        socketTimeoutMS=120000,
        maxPoolSize=20,
        retryWrites=True,
        retryReads=True,
    )


def get_hlhp_db() -> AsyncIOMotorDatabase:
    return _client()[os.getenv("DB_NAME", "skin_bb")]


class _DbProxy:
    def __getitem__(self, name: str):
        return get_hlhp_db()[name]


hl_db = _DbProxy()
