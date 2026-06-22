from __future__ import annotations

from datetime import date
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.core.constants import totalScanIngedientPerDay
from app.label_looker.core.errors import ScannerApiError
from app.label_looker.services.user_profile_flow import user_details_lookup_filter


def _today_key() -> str:
    return date.today().isoformat()


def _read_quota_used(details_doc: dict[str, Any] | None) -> int:
    if not details_doc:
        return 0
    raw = details_doc.get("labelLookerQuota")
    if not isinstance(raw, dict):
        return 0
    if str(raw.get("date") or "") != _today_key():
        return 0
    try:
        return max(0, int(raw.get("used") or 0))
    except (TypeError, ValueError):
        return 0


async def get_daily_quota_snapshot(
    *,
    user_details_coll: AsyncIOMotorCollection,
    user_id: Any,
) -> dict[str, int]:
    doc = await user_details_coll.find_one(user_details_lookup_filter(user_id)) or {}
    used = _read_quota_used(doc)
    return {
        "used": used,
        "limit": totalScanIngedientPerDay,
        "remaining": max(0, totalScanIngedientPerDay - used),
    }


async def assert_daily_quota_available(
    *,
    user_details_coll: AsyncIOMotorCollection,
    user_id: Any,
) -> None:
    snap = await get_daily_quota_snapshot(user_details_coll=user_details_coll, user_id=user_id)
    if snap["used"] >= snap["limit"]:
        raise ScannerApiError(402, "insufficient_credits")


async def record_daily_quota_use(
    *,
    user_details_coll: AsyncIOMotorCollection,
    user_id: Any,
) -> dict[str, int]:
    today = _today_key()
    doc = await user_details_coll.find_one(user_details_lookup_filter(user_id)) or {}
    used = _read_quota_used(doc) + 1
    await user_details_coll.update_one(
        user_details_lookup_filter(user_id),
        {
            "$set": {
                "userId": user_id,
                "labelLookerQuota": {"date": today, "used": used},
                "updatedAt": __import__("datetime").datetime.now(),
            }
        },
        upsert=True,
    )
    return {
        "used": used,
        "limit": totalScanIngedientPerDay,
        "remaining": max(0, totalScanIngedientPerDay - used),
    }
