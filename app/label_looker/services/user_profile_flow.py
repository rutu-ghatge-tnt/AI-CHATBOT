from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.services.profile_form import _age_from_dob as _age_from_dob_field
from app.label_looker.services.profile_form import _parse_age as _parse_age_field

from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.services.profile_taxonomy_resolver import resolve_profile_taxonomy_refs


def user_details_lookup_filter(user_id: Any, *, mongo_user_id: ObjectId | None = None) -> dict[str, Any]:
    """Match common shapes: camelCase userId, snake_case user_id, ObjectId, document _id."""
    uid = str(user_id).strip() if user_id is not None else ""
    clauses: list[dict[str, Any]] = []
    if mongo_user_id is not None:
        clauses.extend(
            (
                {"userId": mongo_user_id},
                {"user_id": mongo_user_id},
            )
        )
    if user_id is not None:
        clauses.extend(({"userId": user_id}, {"user_id": user_id}))
    if uid:
        clauses.extend(({"userId": uid}, {"user_id": uid}))
        if ObjectId.is_valid(uid):
            oid = ObjectId(uid)
            clauses.extend(({"userId": oid}, {"user_id": oid}, {"_id": oid}))
    if not clauses:
        return {"userId": user_id}
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for clause in clauses:
        key = str(sorted(clause.items()))
        if key not in seen:
            seen.add(key)
            unique.append(clause)
    return {"$or": unique} if len(unique) > 1 else unique[0]


def users_lookup_filter(*, user_id: Any, auth_user: dict[str, Any] | None) -> dict[str, Any]:
    """Match `skin_bb.users` by _id, externalId, or profileUrl."""
    clauses: list[dict[str, Any]] = []
    uid = str(user_id).strip() if user_id is not None else ""
    if uid and ObjectId.is_valid(uid):
        clauses.append({"_id": ObjectId(uid)})
    if uid:
        clauses.append({"externalId": uid})
        clauses.append({"profileUrl": uid})
    if auth_user:
        for key in ("externalId", "id", "_id", "userId", "user_id"):
            raw = auth_user.get(key)
            if raw is None:
                continue
            s = str(raw).strip()
            if not s:
                continue
            if ObjectId.is_valid(s):
                clauses.append({"_id": ObjectId(s)})
            else:
                clauses.append({"externalId": s})
        profile_url = auth_user.get("profileUrl")
        if isinstance(profile_url, str) and profile_url.strip():
            clauses.append({"profileUrl": profile_url.strip()})
        front_name = auth_user.get("frontName")
        if isinstance(front_name, str) and front_name.strip():
            clauses.append({"profileUrl": front_name.strip()})
    if not clauses:
        return {"_id": user_id}
    # Deduplicate clause dicts
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for clause in clauses:
        key = str(sorted(clause.items()))
        if key not in seen:
            seen.add(key)
            unique.append(clause)
    return {"$or": unique}


async def resolve_users_collection_id(
    *,
    users_coll: AsyncIOMotorCollection,
    user_id: Any,
    auth_user: dict[str, Any] | None,
) -> ObjectId | None:
    """Map app auth id (UUID externalId) to Mongo `users._id` for user_details joins."""
    account = await users_coll.find_one(users_lookup_filter(user_id=user_id, auth_user=auth_user), projection={"_id": 1})
    if account and account.get("_id") is not None:
        oid = account["_id"]
        return oid if isinstance(oid, ObjectId) else ObjectId(str(oid))
    uid = str(user_id).strip() if user_id is not None else ""
    if uid and ObjectId.is_valid(uid):
        return ObjectId(uid)
    return None


def _unwrap_scalar_array(value: Any) -> Any:
    """Mongo often stores hairType / skinTone as Array(1) — unwrap for form scalars."""
    if isinstance(value, list):
        if not value:
            return None
        if len(value) == 1:
            return value[0]
    return value


def normalize_mongo_profile_shape(details: dict[str, Any]) -> dict[str, Any]:
    """Normalize common SkinBB user_details shapes before form merge."""
    doc = dict(details or {})
    for key in ("hairType", "skinTone", "skinType", "scalpConcern", "gender", "lipType"):
        if key in doc:
            doc[key] = _unwrap_scalar_array(doc.get(key))
    if doc.get("mobile") is None and doc.get("phoneNumber"):
        doc["mobile"] = doc.get("phoneNumber")
    if doc.get("screenTime") is None and doc.get("sleepDurations") is not None:
        doc["screenTime"] = doc.get("sleepDurations")
    if doc.get("screenTime") is None and doc.get("sleepTime") is not None:
        doc["screenTime"] = doc.get("sleepTime")
    if doc.get("age") is None:
        for key in ("bornOn", "born_on", "dateOfBirth", "dob", "birthDate"):
            inferred = _age_from_dob_field(doc.get(key))
            if inferred is not None:
                doc["age"] = inferred
                break
        if doc.get("age") is None:
            for key in ("age", "ageYears", "age_years", "ageValue"):
                parsed = _parse_age_field(doc.get(key))
                if parsed is not None:
                    doc["age"] = parsed
                    break
    return doc


def merge_auth_user_details(details: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """
    Merge Mongo `user_details` with fields already present on the authenticated user
    (Node user-details response) or `users` collection row.
    """
    merged = dict(details or {})
    scalar_keys = (
        "age",
        "gender",
        "skinType",
        "hairType",
        "lipType",
        "firstName",
        "lastName",
        "username",
        "userName",
        "email",
        "mobile",
        "phone",
        "phoneNumber",
        "city",
        "state",
        "country",
        "bio",
        "instagram",
        "bornOn",
        "dateOfBirth",
        "weight",
        "height",
        "skinTone",
        "scalpConcern",
        "environmentAssessment",
        "screenTime",
        "breakPattern",
        "stressLevel",
        "sleepDurations",
    )
    for k in scalar_keys:
        v = merged.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            uval = user.get(k)
            if uval is not None and (not isinstance(uval, str) or str(uval).strip()):
                merged[k] = uval
    if merged.get("mobile") is None and user.get("phoneNumber"):
        merged["mobile"] = user.get("phoneNumber")
    if merged.get("username") is None and user.get("profileUrl"):
        merged["username"] = user.get("profileUrl")
    list_keys = (
        "skinConcerns",
        "skinGoals",
        "hairConcerns",
        "hairGoals",
        "lipConcerns",
        "lipGoals",
        "lifeStages",
        "life_stages",
        "conditions",
        "allergies",
    )
    for k in list_keys:
        cur = merged.get(k)
        if cur is None:
            uval = user.get(k)
            merged[k] = list(uval) if isinstance(uval, list) else ([] if uval is None else [str(uval)])
        elif isinstance(cur, list) and len(cur) == 0:
            uval = user.get(k)
            if isinstance(uval, list) and len(uval) > 0:
                merged[k] = list(uval)
    if merged.get("age") is None and user.get("age") is not None:
        merged["age"] = user.get("age")
    if not str(merged.get("name") or "").strip():
        fn = str(user.get("firstName") or "").strip()
        ln = str(user.get("lastName") or "").strip()
        if fn or ln:
            merged["name"] = f"{fn} {ln}".strip()
    return merged


async def _load_user_account(
    *,
    users_coll: AsyncIOMotorCollection,
    user_id: Any,
    auth_user: dict[str, Any] | None,
) -> dict[str, Any]:
    doc = await users_coll.find_one(users_lookup_filter(user_id=user_id, auth_user=auth_user))
    return dict(doc) if doc else {}


async def load_merged_user_details(
    *,
    user_details_coll: AsyncIOMotorCollection,
    user_id: Any,
    user: dict[str, Any] | None,
    users_coll: AsyncIOMotorCollection | None = None,
) -> dict[str, Any]:
    """
    Load profile from `user_details`, enrich with `users` account row, auth user, and
    resolved taxonomy labels (ObjectId → string).
    """
    mongo_user_id: ObjectId | None = None
    if users_coll is not None:
        mongo_user_id = await resolve_users_collection_id(
            users_coll=users_coll,
            user_id=user_id,
            auth_user=user,
        )

    raw = await user_details_coll.find_one(
        user_details_lookup_filter(user_id, mongo_user_id=mongo_user_id)
    ) or {}
    normalized = normalize_mongo_profile_shape(raw)

    account: dict[str, Any] = {}
    if users_coll is not None:
        account = await _load_user_account(users_coll=users_coll, user_id=user_id, auth_user=user)

    merged = normalized
    if account:
        merged = merge_auth_user_details(merged, account)
    if user:
        merged = merge_auth_user_details(merged, user)

    if users_coll is not None:
        from app.label_looker.core.db import get_scanner_db

        db = get_scanner_db()
        merged = await resolve_profile_taxonomy_refs(db, merged)
    return merged


async def load_full_user_profile(
    *,
    user_id: Any,
    user: dict[str, Any] | None,
) -> dict[str, Any]:
    """Convenience loader used by profile GET / validation — always merges users + taxonomy."""
    from app.label_looker.core.db import get_scanner_db

    s = get_label_looker_settings()
    db = get_scanner_db()
    return await load_merged_user_details(
        user_details_coll=db[s.coll_user_details],
        users_coll=db[s.coll_user],
        user_id=user_id,
        user=user,
    )
