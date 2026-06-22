import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.hlhp.config import hl_settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis  # type: ignore
except Exception:
    redis = None  # type: ignore

_redis_client = None
_memory_cache: dict[str, tuple[float, str]] = {}
_mongo_index_ensured = False

_CACHE_COLLECTION = "hlhp_cache"


async def _ensure_mongo_index() -> None:
    global _mongo_index_ensured
    if _mongo_index_ensured:
        return
    try:
        from app.hlhp.db import hl_db

        col = hl_db[_CACHE_COLLECTION]
        await col.create_index("expires_at", expireAfterSeconds=0)
        await col.create_index("key", unique=True)
        _mongo_index_ensured = True
    except Exception as exc:
        logger.warning("HLHP mongo cache index setup skipped: %s", exc)


async def _get_redis():
    global _redis_client
    if redis is None:
        return None
    if _redis_client is None:
        _redis_client = redis.from_url(hl_settings.REDIS_URL, decode_responses=True)
    return _redis_client


def _memory_get(key: str) -> dict[str, Any] | None:
    now = time.time()
    if key not in _memory_cache:
        return None
    expires_at, payload = _memory_cache[key]
    if now > expires_at:
        _memory_cache.pop(key, None)
        return None
    return json.loads(payload)


def _memory_set(key: str, value: dict[str, Any], ttl: int) -> None:
    _memory_cache[key] = (time.time() + ttl, json.dumps(value, default=str))


async def _mongo_get(key: str) -> dict[str, Any] | None:
    from app.hlhp.db import hl_db

    await _ensure_mongo_index()
    doc = await hl_db[_CACHE_COLLECTION].find_one({"key": key})
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if expires_at and expires_at <= datetime.now(timezone.utc):
        await hl_db[_CACHE_COLLECTION].delete_one({"key": key})
        return None
    payload = doc.get("payload")
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    return None


async def _mongo_set(key: str, value: dict[str, Any], ttl: int) -> None:
    from app.hlhp.db import hl_db

    await _ensure_mongo_index()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    await hl_db[_CACHE_COLLECTION].update_one(
        {"key": key},
        {
            "$set": {
                "key": key,
                "payload": value,
                "expires_at": expires_at,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )


async def _redis_get(key: str) -> dict[str, Any] | None:
    r = await _get_redis()
    if r is None:
        return None
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def _redis_set(key: str, value: dict[str, Any], ttl: int) -> None:
    r = await _get_redis()
    if r is None:
        return
    payload = json.dumps(value, default=str)
    await r.setex(key, ttl, payload)


async def get_cached(key: str) -> dict[str, Any] | None:
    backend = hl_settings.CACHE_BACKEND

    if backend == "redis":
        try:
            hit = await _redis_get(key)
            if hit is not None:
                return hit
        except Exception as exc:
            logger.warning("HLHP redis cache get failed (%s); falling back", exc)

    if backend in {"mongo", "redis"}:
        try:
            hit = await _mongo_get(key)
            if hit is not None:
                return hit
        except Exception as exc:
            logger.warning("HLHP mongo cache get failed (%s); falling back", exc)

    return _memory_get(key)


async def set_cached(key: str, value: dict[str, Any], ttl: int):
    backend = hl_settings.CACHE_BACKEND
    stored = False

    if backend == "redis":
        try:
            await _redis_set(key, value, ttl)
            stored = True
        except Exception as exc:
            logger.warning("HLHP redis cache set failed (%s); trying mongo/memory", exc)

    if backend in {"mongo", "redis"} and not stored:
        try:
            await _mongo_set(key, value, ttl)
            stored = True
        except Exception as exc:
            logger.warning("HLHP mongo cache set failed (%s); using memory", exc)

    if not stored or backend == "memory":
        _memory_set(key, value, ttl)
