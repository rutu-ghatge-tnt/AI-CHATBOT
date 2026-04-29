from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId

from app.label_looker.aggregations import admin_scan_list_pipeline, rating_count_pipeline
from app.label_looker.errors import ScannerApiError
from app.label_looker.settings import get_label_looker_settings


async def analysis_list(*, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    coll = db[s.coll_scan_analysis]
    pipe = admin_scan_list_pipeline(skip=skip, limit=limit, s=s)
    return await coll.aggregate(pipe).to_list(length=limit + 10)


async def analysis_by_id(scan_id: str) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    if not ObjectId.is_valid(scan_id):
        raise ScannerApiError(400, "Invalid id")
    db = get_scanner_db()
    coll = db[s.coll_scan_analysis]
    doc = await coll.find_one({"_id": ObjectId(scan_id)})
    if not doc:
        raise ScannerApiError(404, "Not found")
    return doc


async def analytics_summary() -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    coll = db[s.coll_scan_analysis]
    total = await coll.count_documents({})
    with_error = await coll.count_documents({"scanImageError": {"$ne": None}})
    analyzed = await coll.count_documents({"analyticDetail": {"$exists": True}})
    return {
        "totalScans": total,
        "scansWithImageError": with_error,
        "scansWithAnalysis": analyzed,
        "generatedAt": datetime.now().isoformat(),
    }


async def user_total_scan() -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    coll = db[s.coll_scan_analysis]
    pipe = [
        {"$match": {"userId": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$userId", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 200},
    ]
    rows = await coll.aggregate(pipe).to_list(length=250)
    return {"users": rows}


async def rating_counts() -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    coll = db[s.coll_scan_analysis]
    rows = await coll.aggregate(rating_count_pipeline(s)).to_list(length=10)
    return {"ratings": rows}
