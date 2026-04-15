import json
import time
from typing import Any

from app.hl_engine.config import hl_settings

try:
    import redis.asyncio as redis  # type: ignore
except Exception:
    redis = None  # type: ignore


_redis_client = None
_memory_cache: dict[str, tuple[float, str]] = {}


async def _get_redis():
    global _redis_client
    if redis is None:
        return None
    if _redis_client is None:
        _redis_client = redis.from_url(hl_settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def get_cached(key: str) -> dict[str, Any] | None:
    r = await _get_redis()
    if r is not None:
        raw = await r.get(key)
        return json.loads(raw) if raw else None

    now = time.time()
    if key not in _memory_cache:
        return None
    expires_at, payload = _memory_cache[key]
    if now > expires_at:
        _memory_cache.pop(key, None)
        return None
    return json.loads(payload)


async def set_cached(key: str, value: dict[str, Any], ttl: int):
    payload = json.dumps(value, default=str)
    r = await _get_redis()
    if r is not None:
        await r.setex(key, ttl, payload)
        return
    _memory_cache[key] = (time.time() + ttl, payload)

