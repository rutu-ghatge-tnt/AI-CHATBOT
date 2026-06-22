from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.core.constants import totalScanIngedientPerDay
from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.prompts_controller import scan_image_to_text_prompt
from app.label_looker.text_extract import extract_bracket_string_array
from app.label_looker.upload_utils import public_relative_url


def _local_midnight() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _user_id_for_db(user: dict[str, Any]) -> Any:
    uid = user.get("_id") or user.get("id")
    if uid is None:
        return None
    s = str(uid)
    if ObjectId.is_valid(s) and len(s) == 24:
        return ObjectId(s)
    return s


async def _count_scans_today(coll: AsyncIOMotorCollection, profile_url: str | None) -> int:
    if not profile_url:
        return 0
    start = _local_midnight()
    return await coll.count_documents(
        {
            "createdAt": {"$gte": start},
            "userProfileUrl": profile_url,
            "scanImageError": None,
        }
    )


async def scan_image_to_text(
    *,
    user: dict[str, Any],
    image_bytes: bytes,
    content_type: str,
    image_basename: str,
) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    scan_detail_coll: AsyncIOMotorCollection = db[s.coll_scan_detail]

    from app.label_looker.services.label_looker_quota import (
        assert_daily_quota_available,
        get_daily_quota_snapshot,
        record_daily_quota_use,
    )
    from app.label_looker.services.common_flow import extract_user_id

    user_id = extract_user_id(user)
    user_details_coll = db[s.coll_user_details]
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    await assert_daily_quota_available(user_details_coll=user_details_coll, user_id=user_id)
    snap_before = await get_daily_quota_snapshot(user_details_coll=user_details_coll, user_id=user_id)
    scans_left_after = max(0, snap_before["remaining"] - 1)
    rel_url = public_relative_url(image_basename)
    now = datetime.now()
    base_doc: dict[str, Any] = {
        "userProfileUrl": user.get("profileUrl"),
        "firstName": user.get("firstName"),
        "lastName": user.get("lastName"),
        "userId": _user_id_for_db(user),
        "scanImageUrl": rel_url,
        "extractedIngredients": [],
        "scansLeft": scans_left_after,
        "scanImageError": None,
        "ingredientAnalysisError": None,
        "createdAt": now,
        "updatedAt": now,
    }
    ins = await scan_coll.insert_one(base_doc)
    scan_id = ins.inserted_id

    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        msg = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": scan_image_to_text_prompt()},
                    ],
                }
            ],
        )
        text_parts = []
        for block in msg.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        raw = "".join(text_parts)
        names = extract_bracket_string_array(raw)
        await scan_coll.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "extractedIngredients": names,
                    "scansLeft": scans_left_after,
                    "updatedAt": datetime.now(),
                }
            },
        )
        await scan_detail_coll.insert_one(
            {
                "scanAnalysisId": scan_id,
                "scanImageUrl": rel_url,
                "extractedIngredients": names,
                "createdAt": datetime.now(),
                "updatedAt": datetime.now(),
            }
        )
        await record_daily_quota_use(user_details_coll=user_details_coll, user_id=user_id)
        return {"scanDetail": str(scan_id), "ingredientNames": names}
    except Exception as e:
        await scan_coll.update_one(
            {"_id": scan_id},
            {"$set": {"scanImageError": str(e), "updatedAt": datetime.now()}},
        )
        await scan_detail_coll.insert_one(
            {
                "scanAnalysisId": scan_id,
                "scanImageUrl": rel_url,
                "extractedIngredients": [],
                "scanImageError": str(e),
                "createdAt": datetime.now(),
                "updatedAt": datetime.now(),
            }
        )
        raise ScannerApiError(500, str(e)) from e


async def number_of_scan_left(*, user: dict[str, Any]) -> dict[str, Any]:
    from app.label_looker.core.db import get_scanner_db
    from app.label_looker.services.common_flow import extract_user_id
    from app.label_looker.services.label_looker_quota import get_daily_quota_snapshot

    s = get_label_looker_settings()
    db = get_scanner_db()
    user_id = extract_user_id(user)
    if user_id is None:
        return {"totalScanPerDay": totalScanIngedientPerDay, "scanLeft": totalScanIngedientPerDay}
    snap = await get_daily_quota_snapshot(user_details_coll=db[s.coll_user_details], user_id=user_id)
    return {"totalScanPerDay": snap["limit"], "scanLeft": snap["remaining"]}

