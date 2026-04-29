from __future__ import annotations

from functools import lru_cache

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.label_looker.settings import get_label_looker_settings


@lru_cache
def _client() -> AsyncIOMotorClient:
    s = get_label_looker_settings()
    return AsyncIOMotorClient(
        s.mongo_uri,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=20000,
        socketTimeoutMS=120000,
        maxPoolSize=50,
        minPoolSize=5,
        retryWrites=True,
        retryReads=True,
    )


def get_scanner_db() -> AsyncIOMotorDatabase:
    s = get_label_looker_settings()
    return _client()[s.mongo_database]
