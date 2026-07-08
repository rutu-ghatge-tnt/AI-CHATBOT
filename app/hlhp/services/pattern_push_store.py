"""FCM device token persistence for HLHP pattern pushes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.hlhp.db import hl_db
from app.hlhp.mongo_setup import ensure_hlhp_indexes

logger = logging.getLogger(__name__)

_TOKENS = "hlhp_push_tokens"


async def save_push_token(
    user_id: str,
    token: str,
    *,
    platform: str = "web",
) -> None:
    await ensure_hlhp_indexes()
    if not user_id or not token:
        return
    now = datetime.now(timezone.utc)
    try:
        await hl_db[_TOKENS].update_one(
            {"user_id": user_id, "token": token},
            {
                "$set": {
                    "user_id": user_id,
                    "token": token,
                    "platform": platform,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    except Exception as exc:
        logger.warning("push token save failed user=%s: %s", user_id, exc)


async def get_push_tokens(user_id: str) -> list[str]:
    await ensure_hlhp_indexes()
    if not user_id:
        return []
    out: list[str] = []
    try:
        cursor = hl_db[_TOKENS].find({"user_id": user_id})
        async for doc in cursor:
            tok = str(doc.get("token") or "").strip()
            if tok:
                out.append(tok)
    except Exception as exc:
        logger.warning("push token fetch failed user=%s: %s", user_id, exc)
    return out
