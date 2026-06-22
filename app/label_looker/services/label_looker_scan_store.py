from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _normalize_product_ref,
    _user_product_scan_filter,
)


async def find_user_product_scan(
    *,
    scan_coll: AsyncIOMotorCollection,
    user: dict[str, Any],
    user_id: Any,
    product_ref: Any,
    require_match: bool = False,
) -> dict[str, Any] | None:
    """Latest Label Looker row for this user + catalog product."""
    extra: dict[str, Any] | None = None
    if require_match:
        extra = {"band": {"$exists": True, "$ne": None}}
    doc = await scan_coll.find_one(
        _user_product_scan_filter(
            user=user,
            user_id=user_id,
            product_ref=product_ref,
            extra=extra,
        ),
        sort=[("updatedAt", -1)],
    )
    return doc


def scan_ids_from_doc(doc: dict[str, Any]) -> tuple[str, str]:
    """
    Return (user_scan_id, analysis_scan_id).
    Unified rows use the same id for both; legacy rows may set analysisScanId.
    """
    user_scan_id = str(doc.get("_id"))
    linked = doc.get("analysisScanId") or doc.get("analysis_scan_id")
    analysis_scan_id = str(linked) if linked else user_scan_id
    return user_scan_id, analysis_scan_id


def normalize_product_id(product_id: Any) -> Any | None:
    return _normalize_product_ref(product_id)
