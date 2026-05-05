from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection


def extract_user_id(user: dict[str, Any]) -> Any:
    uid = user.get("_id") or user.get("id")
    if uid is None:
        return None
    s = str(uid)
    if ObjectId.is_valid(s):
        return ObjectId(s)
    return s


def local_midnight() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


async def count_scans_today(coll: AsyncIOMotorCollection, profile_url: str | None) -> int:
    if not profile_url:
        return 0
    start = local_midnight()
    return await coll.count_documents(
        {
            "createdAt": {"$gte": start},
            "userProfileUrl": profile_url,
            "scanImageError": None,
        }
    )
