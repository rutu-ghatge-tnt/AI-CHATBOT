from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

_NAME_KEYS = ("name", "title", "label", "value", "slug", "concernName", "hairTypeName", "skinTypeName")


def _normalize_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    if isinstance(value, dict):
        oid = value.get("$oid") or value.get("_id")
        if isinstance(oid, str) and ObjectId.is_valid(oid):
            return ObjectId(oid)
        if isinstance(oid, ObjectId):
            return oid
    return None


def _label_from_doc(doc: dict[str, Any]) -> str | None:
    for key in _NAME_KEYS:
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _collect_object_ids(raw: Any) -> list[ObjectId]:
    ids: list[ObjectId] = []
    if isinstance(raw, list):
        for item in raw:
            oid = _normalize_object_id(item)
            if oid is not None:
                ids.append(oid)
    else:
        oid = _normalize_object_id(raw)
        if oid is not None:
            ids.append(oid)
    return list(dict.fromkeys(ids))


_TAXONOMY_COLLECTIONS = (
    "product_skin_concerns",
    "skin_concerns",
    "product_hair_concerns",
    "hair_concerns",
    "product_hair_types",
    "hair_types",
    "product_skin_types",
    "skin_types",
    "skin_benefits",
    "hair_benefits",
    "skin_goals",
    "hair_goals",
    "skin_tones",
    "product_skin_tones",
    "product_attributes",
    "product_attribute_values",
    "benefits",
    "categories",
)


def _slug_from_taxonomy_doc(doc: dict[str, Any]) -> str | None:
    """Prefer canonical Mongo `value` slug; fall back to label / name."""
    val = doc.get("value")
    if isinstance(val, str) and val.strip():
        return val.strip()
    slug = doc.get("slug")
    if isinstance(slug, str) and slug.strip():
        return slug.strip()
    return _label_from_doc(doc)


async def _resolve_object_ids(db: AsyncIOMotorDatabase, ids: list[ObjectId]) -> dict[ObjectId, str]:
    if not ids:
        return {}
    resolved: dict[ObjectId, str] = {}
    pending = list(ids)
    for coll_name in _TAXONOMY_COLLECTIONS:
        if not pending:
            break
        coll = db[coll_name]
        cursor = coll.find(
            {"_id": {"$in": pending}},
            {"name": 1, "title": 1, "label": 1, "value": 1, "slug": 1},
        )
        async for doc in cursor:
            oid = doc.get("_id")
            if not isinstance(oid, ObjectId):
                continue
            label = _slug_from_taxonomy_doc(doc)
            if label:
                resolved[oid] = label
        pending = [oid for oid in pending if oid not in resolved]
    return resolved


def _resolve_list_values(raw: Any, resolved: dict[ObjectId, str]) -> list[str]:
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
            continue
        if isinstance(item, dict):
            labeled = False
            for key in _NAME_KEYS:
                v = item.get(key)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                    labeled = True
                    break
            if labeled:
                continue
            # Extended-JSON / API-shaped refs: {"$oid": "..."} or {"_id": "..."}
            oid = _normalize_object_id(item)
            if oid is not None:
                label = resolved.get(oid)
                if label:
                    out.append(label)
            continue
        oid = _normalize_object_id(item)
        if oid is not None:
            label = resolved.get(oid)
            if label:
                out.append(label)
    return list(dict.fromkeys(out))


async def resolve_product_catalog_labels(
    *,
    db: AsyncIOMotorDatabase,
    product: dict[str, Any],
    keys: tuple[str, ...] | list[str],
) -> list[str]:
    """Resolve product catalog list fields that may be ObjectId refs, dicts, or strings.

    Same class of bug as unresolved ``benefit`` ObjectIds: PDP populates labels,
    but Label Looker scoring historically kept only bare strings and dropped refs.
    """
    combined: list[Any] = []
    for key in keys:
        raw = product.get(key)
        if isinstance(raw, list):
            combined.extend(raw)
        elif isinstance(raw, str) and raw.strip():
            combined.append(raw.strip())
        elif raw is not None and not isinstance(raw, (list, dict)):
            # Bare ObjectId scalar
            combined.append(raw)
        elif isinstance(raw, dict):
            combined.append(raw)
    if not combined:
        return []
    ids = _collect_object_ids(combined)
    resolved = await _resolve_object_ids(db, ids) if ids else {}
    return _resolve_list_values(combined, resolved)


def _resolve_scalar_value(raw: Any, resolved: dict[ObjectId, str]) -> Any:
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            return None
        return _resolve_scalar_value(raw[0], resolved)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, (int, float, bool)):
        return raw
    if isinstance(raw, dict):
        for key in _NAME_KEYS:
            v = raw.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        oid = _normalize_object_id(raw)
        if oid is not None and oid in resolved:
            return resolved[oid]
    oid = _normalize_object_id(raw)
    if oid is not None:
        return resolved.get(oid) or str(oid)
    return raw


async def resolve_profile_taxonomy_refs(db: AsyncIOMotorDatabase, details: dict[str, Any]) -> dict[str, Any]:
    """Resolve ObjectId refs in user_details into human-readable strings for forms."""
    doc = dict(details or {})
    id_fields = (
        "skinConcerns",
        "skinGoals",
        "hairConcerns",
        "hairGoals",
        "hairType",
        "skinType",
        "skinTone",
        "scalpConcern",
        "scalpConcerns",
        "lipConcerns",
        "lipGoals",
    )
    all_ids: list[ObjectId] = []
    for field in id_fields:
        all_ids.extend(_collect_object_ids(doc.get(field)))
    resolved = await _resolve_object_ids(db, list(dict.fromkeys(all_ids)))

    list_fields = ("skinConcerns", "skinGoals", "hairConcerns", "hairGoals", "lipConcerns", "lipGoals", "scalpConcerns")
    scalar_fields = ("skinType", "hairType", "skinTone", "scalpConcern", "lipType")

    for field in list_fields:
        if field in doc or doc.get(field) is not None:
            vals = _resolve_list_values(doc.get(field), resolved)
            if vals:
                doc[field] = vals
    for field in scalar_fields:
        if field in doc or doc.get(field) is not None:
            val = _resolve_scalar_value(doc.get(field), resolved)
            if val is not None and (not isinstance(val, str) or val.strip()):
                doc[field] = val
    return doc
