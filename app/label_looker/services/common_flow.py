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


def end_user_owns_scan_document(doc: dict[str, Any], user: dict[str, Any], user_id: Any) -> bool:
    """
    Match / analysis scan rows may store legacy Mongo userId while app auth uses UUID (externalId).
    Treat userProfileUrl vs profileUrl (and a few aliases) as a stable alternate owner key.
    """
    if str(doc.get("userId") or "") == str(user_id or ""):
        return True
    for alt_key in ("externalId", "id", "_id"):
        alt = user.get(alt_key)
        if alt is not None and str(doc.get("userId") or "") == str(alt):
            return True
    doc_profile = str(doc.get("userProfileUrl") or "").strip().lower()
    if not doc_profile:
        return False
    for key in ("profileUrl", "username", "email", "frontName"):
        v = user.get(key)
        if isinstance(v, str) and v.strip().lower() == doc_profile:
            return True
    return False


def scan_document_has_owner(doc: dict[str, Any]) -> bool:
    if doc.get("userId") is not None and str(doc.get("userId")).strip():
        return True
    return bool(str(doc.get("userProfileUrl") or "").strip())


def require_end_user_owns_scan(
    *,
    doc: dict[str, Any],
    user: dict[str, Any] | None,
    user_id: Any,
) -> None:
    """Raise 403/401 when a scan row is owned by another user."""
    from app.label_looker.core.errors import ScannerApiError

    if not scan_document_has_owner(doc):
        return
    if user is None or user_id is None:
        raise ScannerApiError(401, "Please login to access this scan")
    if not end_user_owns_scan_document(doc, user, user_id):
        raise ScannerApiError(403, "Forbidden")


def user_owned_scans_filter(*, user: dict[str, Any], user_id: Any) -> dict[str, Any]:
    """Mongo filter for scan history — matches userId and legacy userProfileUrl rows."""
    clauses: list[dict[str, Any]] = [{"userId": user_id}]
    uid = str(user_id).strip() if user_id is not None else ""
    if uid and ObjectId.is_valid(uid):
        clauses.append({"userId": ObjectId(uid)})
    for alt_key in ("externalId", "id", "_id"):
        alt = user.get(alt_key)
        if alt is not None:
            clauses.append({"userId": alt})
            s = str(alt).strip()
            if s and ObjectId.is_valid(s):
                clauses.append({"userId": ObjectId(s)})
    profile_url = user.get("profileUrl")
    if isinstance(profile_url, str) and profile_url.strip():
        clauses.append({"userProfileUrl": profile_url.strip()})
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for clause in clauses:
        key = str(sorted(clause.items()))
        if key not in seen:
            seen.add(key)
            unique.append(clause)
    return {"$or": unique} if len(unique) > 1 else unique[0]


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
