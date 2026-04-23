from __future__ import annotations

import logging
import os
from datetime import datetime
import re
from typing import Any

from anthropic import AsyncAnthropic
from bson import ObjectId
import httpx
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.constants import DEFAULT_LANGUAGE, totalScanIngedientPerDay
from app.label_looker.errors import ScannerApiError
from app.label_looker.prompts_controller import ingredient_analysis_user_message
from app.label_looker.settings import get_label_looker_settings
from app.label_looker.text_extract import extract_first_json_object
from app.label_looker.tile_content_generator import (
    TileGenerationError,
    build_fallback_tiles,
    generate_tile_content,
)

logger = logging.getLogger(__name__)


GENERIC_ANALYSIS_FAIL = "There's no data available right now. Please try again later."
_VALID_MODES = {"skincare", "haircare", "lipcare"}


def _local_midnight() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


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


def _normalize_mode(*, product_for: Any, specific_type: Any, main_benefit: Any, mode_hint: Any = None) -> str:
    hint = str(mode_hint or "").strip().lower()
    if hint in _VALID_MODES:
        return hint
    text = " ".join([str(product_for or ""), str(specific_type or ""), str(main_benefit or "")]).lower()
    lip_keywords = ["lip", "lips", "lipcare", "lip care", "lip balm", "lip mask", "lip serum", "lip scrub"]
    if any(k in text for k in lip_keywords):
        return "lipcare"
    hair_keywords = ["hair", "scalp", "dandruff", "frizz", "fall", "strand", "follicle"]
    return "haircare" if any(k in text for k in hair_keywords) else "skincare"


def _infer_mode_from_product(product: dict[str, Any] | None) -> str | None:
    if not product:
        return None
    # lipcare first, because lip products can also carry generic skin fields.
    ptype = str(product.get("productType") or "").lower()
    pname = str(product.get("productName") or "").lower()
    if "lip" in ptype or "lip" in pname:
        return "lipcare"
    if _product_list_values(product, "lipTypes", "lipType"):
        return "lipcare"
    if _product_list_values(product, "lipConcerns"):
        return "lipcare"
    if _product_list_values(product, "hairTypes", "hairType"):
        return "haircare"
    if _product_list_values(product, "hairConcerns"):
        return "haircare"
    if _product_list_values(product, "skinTypes", "skinType"):
        return "skincare"
    if _product_list_values(product, "skinConcerns"):
        return "skincare"
    if "hair" in ptype or "scalp" in ptype:
        return "haircare"
    if "skin" in ptype or "face" in ptype:
        return "skincare"
    return None


def _product_list_values(product: dict[str, Any] | None, *keys: str) -> list[str]:
    if not product:
        return []
    out: list[str] = []
    for key in keys:
        raw = product.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            val = item.get("value")
            label = item.get("label")
            name = item.get("name")
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
            elif isinstance(label, str) and label.strip():
                out.append(label.strip())
            elif isinstance(name, str) and name.strip():
                out.append(name.strip())
    return list(dict.fromkeys(out))


def _normalize_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    if isinstance(value, dict):
        oid = value.get("$oid")
        if isinstance(oid, str) and ObjectId.is_valid(oid):
            return ObjectId(oid)
    return None


def _metadata_value(product: dict[str, Any] | None, key: str) -> Any:
    if not product:
        return None
    rows = product.get("metaData")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("key") or "").strip().lower() == key.strip().lower():
            return row.get("value")
    return None


def _best_product_type(product: dict[str, Any] | None) -> str | None:
    if not product:
        return None
    ptype = product.get("productType")
    if isinstance(ptype, str) and ptype.strip():
        return ptype.strip()
    md = _metadata_value(product, "product-type")
    if isinstance(md, str) and md.strip():
        return md.strip()
    return None


def _best_main_benefit(product: dict[str, Any] | None) -> str | None:
    if not product:
        return None
    values = _product_list_values(product, "benefit", "claims")
    if values:
        return ", ".join(values)
    return None


async def _fetch_product_by_id(
    *,
    products_coll: AsyncIOMotorCollection,
    product_id: Any,
) -> dict[str, Any] | None:
    if not product_id:
        return None
    pid = str(product_id).strip()
    query: dict[str, Any]
    if ObjectId.is_valid(pid):
        query = {"_id": ObjectId(pid)}
    else:
        query = {"_id": pid}
    return await products_coll.find_one(query)


async def _ingredients_from_product(
    *,
    product: dict[str, Any] | None,
    branded_ingredients_coll: AsyncIOMotorCollection | None = None,
    ingredient_coll: AsyncIOMotorCollection | None = None,
) -> list[str]:
    return await _resolve_ingredient_names_from_rows(
        rows=(product or {}).get("ingredients"),
        branded_ingredients_coll=branded_ingredients_coll,
        ingredient_coll=ingredient_coll,
    )


async def _key_ingredients_from_product(
    *,
    product: dict[str, Any] | None,
    branded_ingredients_coll: AsyncIOMotorCollection | None = None,
    ingredient_coll: AsyncIOMotorCollection | None = None,
) -> list[str]:
    return await _resolve_ingredient_names_from_rows(
        rows=(product or {}).get("keyIngredients"),
        branded_ingredients_coll=branded_ingredients_coll,
        ingredient_coll=ingredient_coll,
    )


async def _resolve_ingredient_names_from_rows(
    *,
    rows: Any,
    branded_ingredients_coll: AsyncIOMotorCollection | None = None,
    ingredient_coll: AsyncIOMotorCollection | None = None,
) -> list[str]:
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    ref_ids: list[ObjectId] = []
    for r in rows:
        if isinstance(r, dict):
            n = str(r.get("name") or "").strip()
            if n:
                out.append(n)
                continue
            oid = _normalize_object_id(r)
            if oid is not None:
                ref_ids.append(oid)
        elif isinstance(r, str) and r.strip():
            oid = _normalize_object_id(r.strip())
            if oid is not None:
                ref_ids.append(oid)
            else:
                out.append(r.strip())
        else:
            oid = _normalize_object_id(r)
            if oid is not None:
                ref_ids.append(oid)

    resolved: dict[ObjectId, str] = {}
    dedup_ref_ids = list(dict.fromkeys(ref_ids))
    if dedup_ref_ids and branded_ingredients_coll is not None:
        cursor = branded_ingredients_coll.find(
            {"_id": {"$in": dedup_ref_ids}},
            {"ingredient_name": 1, "name": 1, "inci_name": 1},
        )
        async for doc in cursor:
            name = (
                str(doc.get("ingredient_name") or "").strip()
                or str(doc.get("name") or "").strip()
                or str(doc.get("inci_name") or "").strip()
            )
            if name:
                resolved[doc.get("_id")] = name

    unresolved = [oid for oid in dedup_ref_ids if oid not in resolved]
    if unresolved and ingredient_coll is not None:
        cursor = ingredient_coll.find(
            {"_id": {"$in": unresolved}},
            {"name": 1, "ingredient_name": 1, "inci_name": 1},
        )
        async for doc in cursor:
            name = (
                str(doc.get("name") or "").strip()
                or str(doc.get("ingredient_name") or "").strip()
                or str(doc.get("inci_name") or "").strip()
            )
            if name:
                resolved[doc.get("_id")] = name

    for oid in dedup_ref_ids:
        name = resolved.get(oid)
        if name:
            out.append(name)
    return list(dict.fromkeys(out))


def _apply_db_key_ingredients(analytic: dict[str, Any], db_key_ingredients: list[str]) -> dict[str, Any]:
    if not db_key_ingredients:
        return analytic
    out = dict(analytic or {})
    out["keyIngredients"] = [{"name": name, "ingredient_name": name} for name in db_key_ingredients]
    return out


def _resolve_analysis_mode(
    *,
    body: dict[str, Any],
    product: dict[str, Any] | None,
    specific_type: Any,
    main_benefit: Any,
) -> str:
    by_product = _infer_mode_from_product(product)
    if by_product:
        return by_product
    return _normalize_mode(
        product_for=body.get("productFor"),
        specific_type=specific_type,
        main_benefit=main_benefit,
        mode_hint=body.get("mode"),
    )


def _required_fields_for_mode(mode: str) -> list[str]:
    if mode == "haircare":
        return ["age", "gender", "hairType", "hairConcerns"]
    if mode == "lipcare":
        # lipcare keeps away from hair fields; prioritize lip fields, fallback to skin fields.
        return ["age", "gender", "lipType", "lipConcerns"]
    return ["age", "gender", "skinType", "skinConcerns"]


def _current_field_value(details: dict[str, Any], mode: str, field: str) -> Any:
    if field in ("age", "gender"):
        return details.get(field)
    if mode == "lipcare":
        if field in ("lipType", "lipConcerns"):
            # Backward compatibility: if lip-specific data isn't stored yet, use skin profile.
            return details.get(field) or details.get("skinType" if field == "lipType" else "skinConcerns")
        return details.get(field)
    if mode == "skincare" and field in ("skinType", "skinConcerns"):
        return details.get(field)
    if mode == "haircare" and field in ("hairType", "hairConcerns"):
        return details.get(field)
    return None


def _pick_two_fields(required_fields: list[str], final_values: dict[str, Any], attempts: dict[str, list[Any]]) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for f in required_fields:
        if f in final_values:
            continue
        a = attempts.get(f) or []
        ranked.append((len(a), f))
    ranked.sort(key=lambda x: (x[0], x[1]))
    return [f for _, f in ranked[:2]]


def _is_present_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def _has_missing_required(details: dict[str, Any], mode: str, final_values: dict[str, Any]) -> bool:
    for f in _required_fields_for_mode(mode):
        val = _current_field_value(details, mode, f)
        if not _is_present_value(val):
            return True
    return False


async def _upsert_validation_state(
    *,
    user_details_coll: AsyncIOMotorCollection,
    user_id: Any,
    mode: str,
    bump_scan_count: bool,
    details_doc: dict[str, Any] | None,
) -> dict[str, Any]:
    details = details_doc or {}
    llv = dict(details.get("labelLookerValidation") or {})
    mode_state = dict(llv.get(mode) or {})
    if bump_scan_count:
        mode_state["scanCount"] = int(mode_state.get("scanCount") or 0) + 1
    else:
        mode_state["scanCount"] = int(mode_state.get("scanCount") or 0)
    # If required data already exists in user details, this mode is effectively finalized.
    if not _has_missing_required(details, mode, dict(mode_state.get("finalValues") or {})):
        mode_state["finalized"] = True
    else:
        mode_state.setdefault("finalized", False)
    mode_state.setdefault("promptRounds", 0)
    mode_state.setdefault("attempts", {})
    mode_state.setdefault("finalValues", {})
    llv[mode] = mode_state
    await user_details_coll.update_one(
        {"userId": user_id},
        {"$set": {"userId": user_id, "labelLookerValidation": llv, "updatedAt": datetime.now()}},
        upsert=True,
    )
    return mode_state


def _build_prompt_payload(
    *,
    mode: str,
    mode_state: dict[str, Any],
    details: dict[str, Any],
    force_prompt_if_missing: bool = False,
) -> dict[str, Any]:
    required_fields = _required_fields_for_mode(mode)
    attempts = dict(mode_state.get("attempts") or {})
    final_values = dict(mode_state.get("finalValues") or {})
    if bool(mode_state.get("finalized")):
        return {"shouldPrompt": False, "mode": mode, "finalized": True, "fields": []}
    if not _has_missing_required(details, mode, final_values):
        return {"shouldPrompt": False, "mode": mode, "finalized": True, "fields": []}
    if not force_prompt_if_missing and int(mode_state.get("scanCount") or 0) % 2 != 0:
        return {"shouldPrompt": False, "mode": mode, "finalized": False, "fields": []}
    fields = _pick_two_fields(required_fields, final_values, attempts)
    if not fields:
        return {"shouldPrompt": False, "mode": mode, "finalized": False, "fields": []}
    return {
        "shouldPrompt": True,
        "mode": mode,
        "finalized": False,
        "fields": fields,
        "promptReason": "After every 2 scans, verify profile data for integrity.",
    }


def _extract_answer_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("value", "label", "name"):
            v = value.get(key)
            if _is_present_value(v):
                return v
    return value


def _normalize_answer_value(field: str, value: Any) -> Any:
    if field == "age":
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            # Accept plain integer input; if user sends a range string, use the first bound.
            m = re.search(r"\d+", raw)
            if m:
                try:
                    return int(m.group(0))
                except ValueError:
                    return None
            return None
    return value


def _normalize_answer_key(mode: str, key: str) -> str:
    canonical = str(key or "").strip().lower().replace("_", "")
    if canonical == "age":
        return "age"
    if canonical == "gender":
        return "gender"
    if canonical in {"skintype"}:
        return "skinType"
    if canonical in {"skinconcerns"}:
        return "skinConcerns"
    if canonical in {"hairtype"}:
        return "hairType"
    if canonical in {"hairconcerns"}:
        return "hairConcerns"
    if canonical in {"liptype"}:
        return "lipType"
    if canonical in {"lipconcerns"}:
        return "lipConcerns"
    return key


def _canonical_for_compare(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(sorted(_canonical_for_compare(v) for v in value))
    return str(value or "").strip().lower()


def _same_answer_value(a: Any, b: Any) -> bool:
    return _canonical_for_compare(a) == _canonical_for_compare(b)


def _apply_answers_to_state(
    mode: str,
    mode_state: dict[str, Any],
    answers: dict[str, Any],
    *,
    details: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    required = set(_required_fields_for_mode(mode))
    attempts = dict(mode_state.get("attempts") or {})
    final_values = dict(mode_state.get("finalValues") or {})
    updates_for_details: dict[str, Any] = {}
    details = details or {}

    for raw_field, raw_value in answers.items():
        field = _normalize_answer_key(mode, str(raw_field))
        if field not in required:
            continue
        if field in final_values:
            continue
        value = _extract_answer_value(raw_value)
        value = _normalize_answer_value(field, value)
        if not _is_present_value(value):
            continue
        key = field
        arr = list(attempts.get(key) or [])
        arr.append(value)
        attempts[key] = arr
        # If user already has the same value saved, accept immediately.
        existing = _current_field_value(details, mode, field)
        if _is_present_value(existing) and _same_answer_value(existing, value):
            final_values[key] = value
            updates_for_details[field] = value
            continue
        if len(arr) >= 3:
            final_values[key] = arr[-1]
            updates_for_details[field] = arr[-1]
            continue
        if len(arr) == 2 and _same_answer_value(arr[0], arr[1]):
            final_values[key] = arr[1]
            updates_for_details[field] = arr[1]

    mode_state["attempts"] = attempts
    mode_state["finalValues"] = final_values
    mode_state["promptRounds"] = int(mode_state.get("promptRounds") or 0) + 1
    if all(f in final_values for f in _required_fields_for_mode(mode)):
        mode_state["finalized"] = True
    return mode_state, updates_for_details


def _profile_sync_payload(updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "age",
        "gender",
        "skinType",
        "skinConcerns",
        "hairType",
        "hairConcerns",
        "lipType",
        "lipConcerns",
    }
    payload: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if not _is_present_value(value):
            continue
        payload[key] = value
    return payload


async def _sync_profile_to_user_service(*, token: str | None, updates: dict[str, Any]) -> None:
    if not token:
        return
    payload = _profile_sync_payload(updates)
    if not payload:
        return
    s = get_label_looker_settings()
    url = f"{s.skin_bb_base_url_norm}/api/v1/users/on-fly/edit-user-detail"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "Profile sync failed status=%s body=%s payload=%s",
                resp.status_code,
                resp.text[:400],
                payload,
            )
    except Exception:
        logger.exception("Profile sync request failed payload=%s", payload)


def _normalize_analysis_payload(parsed: dict[str, Any], fallback_ingredients: Any) -> tuple[dict[str, Any], list[Any]]:
    """
    Accept both payload styles:
    1) { analyticDetail, ingredients } (older contract)
    2) prompt-driven object with keys like opinion/keyIngredients/.../ingredientCategorization
    """
    analytic = parsed.get("analyticDetail")
    ing_out = parsed.get("ingredients")
    if analytic is not None and ing_out is not None:
        return analytic, ing_out if isinstance(ing_out, list) else [ing_out]

    # New prompt shape: store full JSON as analyticDetail and keep ingredients list from request/scan.
    analytic = parsed
    if isinstance(fallback_ingredients, list):
        ing_list = fallback_ingredients
    elif fallback_ingredients is None:
        ing_list = []
    else:
        ing_list = [fallback_ingredients]
    return analytic, ing_list


def _ingredient_list_from_text(raw: str) -> list[str]:
    cleaned = re.sub(r"<[^>]+>", " ", str(raw))
    cleaned = cleaned.replace("&amp;", "&")
    parts = []
    for token in cleaned.replace("\n", ",").replace(";", ",").split(","):
        t = token.strip()
        if t:
            parts.append(t)
    # de-dupe while preserving order
    return list(dict.fromkeys(parts))


def _extract_user_id(user: dict[str, Any]) -> Any:
    uid = user.get("_id") or user.get("id")
    if uid is None:
        return None
    s = str(uid)
    if ObjectId.is_valid(s):
        return ObjectId(s)
    return s


def _normalize_product_ref(product_id: Any) -> Any | None:
    if product_id is None:
        return None
    if isinstance(product_id, ObjectId):
        return product_id
    s = str(product_id).strip()
    if not s:
        return None
    if ObjectId.is_valid(s):
        return ObjectId(s)
    return s


def _as_http_url(value: Any) -> str | None:
    if isinstance(value, str):
        v = value.strip()
        if v.startswith("http://") or v.startswith("https://"):
            return v
    return None


def _resolve_image_url(raw: Any, *, base_url: str) -> str | None:
    direct = _as_http_url(raw)
    if direct:
        return direct
    if isinstance(raw, dict):
        for key in ("url", "imageUrl", "thumbnailUrl", "location", "src"):
            url_val = _as_http_url(raw.get(key))
            if url_val:
                return url_val
        id_like = raw.get("_id") or raw.get("id")
        if id_like:
            return _resolve_image_url(id_like, base_url=base_url)
        return None
    if isinstance(raw, str):
        v = raw.strip()
        if not v:
            return None
        if v.startswith("/"):
            return f"{base_url.rstrip('/')}{v}"
        # Common case in product docs: media ObjectId only.
        if ObjectId.is_valid(v):
            return f"{base_url.rstrip('/')}/api/v1/media/{v}"
    return None


async def _find_cached_non_personalized_analysis(
    *,
    scan_coll: AsyncIOMotorCollection,
    product_ref: Any | None,
) -> dict[str, Any] | None:
    if product_ref is None:
        return None
    doc = await scan_coll.find_one(
        {
            "productId": product_ref,
            "personalizedMatching": {"$ne": True},
            "analyticDetail": {"$exists": True, "$ne": None},
            "ingredientAnalysisError": None,
        },
        sort=[("updatedAt", -1)],
    )
    if not doc:
        return None
    if not isinstance(doc.get("analyticDetail"), dict):
        return None
    return doc


def _build_personalization_context(details: dict[str, Any]) -> str:
    keys = [
        "skinType",
        "skinConcerns",
        "skinGoals",
        "skinTone",
        "lipType",
        "lipConcerns",
        "lipGoals",
        "hairType",
        "hairConcerns",
        "hairGoals",
        "sleepDurations",
        "dietaryPreference",
        "stressLevel",
    ]
    lines = []
    for k in keys:
        if k in details:
            lines.append(f"- {k}: {details.get(k)}")
    return "\n".join(lines)


def _ensure_profile_match_insights(analytic: dict[str, Any], *, personalized: bool) -> dict[str, Any]:
    if not personalized:
        return analytic
    out = dict(analytic or {})
    pmi = out.get("profileMatchInsights")
    if not isinstance(pmi, dict):
        pmi = {}
    pmi.setdefault("worksForUser", "partial")
    pmi.setdefault("matchScore", 50)
    pmi.setdefault(
        "summary",
        "Profile-based match generated. Please review benefits, cautions, and usage guidance for this user.",
    )
    pmi.setdefault("whyItWorks", [])
    pmi.setdefault("possibleRisks", [])
    pmi.setdefault("forThisUserBestUse", [])
    pmi.setdefault("betterAlternativeDirection", [])
    out["profileMatchInsights"] = pmi
    return out


def _detail_labels_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
            continue
        if isinstance(item, dict):
            for key in ("value", "label", "name"):
                v = item.get(key)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                    break
    return list(dict.fromkeys(out))


def _scalar_detail_field(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("label", "value", "name"):
            v = raw.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return str(raw or "").strip()


def _ll2_user_from_details(details: dict[str, Any]) -> dict[str, Any]:
    concerns = _detail_labels_list(details.get("skinConcerns"))
    benefits = _detail_labels_list(details.get("skinGoals"))
    life = details.get("lifeStages") or details.get("life_stages") or []
    if not isinstance(life, list):
        life = []
    life_stages = [str(x).strip() for x in life if str(x).strip()]
    age = details.get("age", "—")
    if age is not None and not isinstance(age, (str, int, float)):
        age = str(age)
    return {
        "age": age if age not in (None, "") else "—",
        "gender": _scalar_detail_field(details.get("gender")) or "—",
        "skin_type": _scalar_detail_field(details.get("skinType")) or "—",
        "concerns": concerns,
        "benefits": benefits,
        "life_stages": life_stages,
    }


def _product_brand_display(product: dict[str, Any]) -> str:
    for key in ("brandName", "brand_name", "brandTitle"):
        v = product.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    brand_ref = product.get("brand")
    if isinstance(brand_ref, dict):
        n = str(brand_ref.get("name") or "").strip()
        if n:
            return n
    return "—"


def _ll2_key_ingredients_from_product(product: dict[str, Any]) -> list[dict[str, Any]]:
    rows = product.get("keyIngredients") or product.get("key_ingredients")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        pos = row.get("position", idx)
        try:
            pos_int = int(pos)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pos_int = idx
        name = (
            str(row.get("inci_name") or "").strip()
            or str(row.get("ingredient_name") or "").strip()
            or str(row.get("name") or "").strip()
        )
        if not name:
            continue
        entry: dict[str, Any] = {
            "position": pos_int,
            "inci_name": name,
            "functions": row.get("functions") if isinstance(row.get("functions"), list) else [],
            "addresses": row.get("addresses") if isinstance(row.get("addresses"), list) else [],
        }
        if row.get("declared_percentage") is not None:
            try:
                entry["declared_percentage"] = float(row["declared_percentage"])
            except (TypeError, ValueError):
                pass
        out.append(entry)
    return out


def _ll2_product_shell_from_mongo(product: dict[str, Any] | None) -> dict[str, Any]:
    if not product:
        return {
            "brand": "—",
            "name": "—",
            "category": "—",
            "declared_for_skin_types": [],
            "claims": [],
            "key_ingredients": [],
        }
    ptype = product.get("productType")
    category = ptype.strip() if isinstance(ptype, str) and ptype.strip() else "—"
    name = str(product.get("productName") or product.get("name") or "—").strip() or "—"
    declared = [x.lower() for x in _product_list_values(product, "skinTypes", "skinType")]
    claims = _product_list_values(product, "benefit", "claims")
    return {
        "brand": _product_brand_display(product),
        "name": name,
        "category": category,
        "declared_for_skin_types": declared,
        "claims": claims,
        "key_ingredients": _ll2_key_ingredients_from_product(product),
    }


def _normalize_ll2_product_overlay(overlay: dict[str, Any]) -> dict[str, Any]:
    """Accept snake_case or camelCase keys from clients."""
    out: dict[str, Any] = dict(overlay)
    if "keyIngredients" in overlay and "key_ingredients" not in overlay:
        out["key_ingredients"] = overlay["keyIngredients"]
    if "declaredForSkinTypes" in overlay and "declared_for_skin_types" not in overlay:
        out["declared_for_skin_types"] = overlay["declaredForSkinTypes"]
    if "productName" in overlay and "name" not in overlay:
        out["name"] = overlay["productName"]
    return out


def _build_ll2_tile_inputs(
    body: dict[str, Any],
    *,
    details_doc: dict[str, Any] | None,
    product: dict[str, Any] | None,
) -> dict[str, Any] | None:
    raw = body.get("ll2TileContentInputs")
    if not isinstance(raw, dict):
        return None
    scoring = raw.get("scoring")
    if not isinstance(scoring, dict):
        return None
    state = scoring.get("state")
    if not isinstance(state, str) or not state.strip():
        return None

    user_overlay = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    base_user = _ll2_user_from_details(details_doc or {})
    user_payload = {**base_user, **user_overlay}
    for key in ("concerns", "benefits", "life_stages"):
        if isinstance(user_overlay.get(key), list) and user_overlay.get(key):
            user_payload[key] = user_overlay[key]

    product_overlay = _normalize_ll2_product_overlay(raw["product"]) if isinstance(raw.get("product"), dict) else {}
    base_product = _ll2_product_shell_from_mongo(product)
    product_payload = {**base_product, **{k: v for k, v in product_overlay.items() if v not in (None, "", [])}}
    if isinstance(product_overlay.get("key_ingredients"), list) and product_overlay["key_ingredients"]:
        product_payload["key_ingredients"] = product_overlay["key_ingredients"]

    observations = raw.get("observations")
    if observations is None:
        observations_list: list[dict[str, Any]] = []
    elif isinstance(observations, list):
        observations_list = [o for o in observations if isinstance(o, dict)]
    else:
        observations_list = []

    return {
        "user": user_payload,
        "product": product_payload,
        "scoring": scoring,
        "observations": observations_list,
    }


async def _maybe_attach_ll2_tile_content(
    *,
    analytic: dict[str, Any],
    body: dict[str, Any],
    details_doc: dict[str, Any] | None,
    product: dict[str, Any] | None,
    client: AsyncAnthropic,
    anthropic_model: str,
) -> dict[str, Any]:
    inputs = _build_ll2_tile_inputs(body, details_doc=details_doc, product=product)
    if inputs is None:
        return analytic
    out = dict(analytic)
    tile_model = (os.getenv("LL2_TILE_ANTHROPIC_MODEL") or "").strip() or anthropic_model
    meta: dict[str, Any] = {"source": "claude", "model": tile_model}
    try:
        tiles = await generate_tile_content(inputs=inputs, client=client, model=tile_model)
    except TileGenerationError as exc:
        logger.warning("LL2 tile generation failed, using template fallback: %s", exc)
        tiles = build_fallback_tiles(inputs=inputs)
        meta = {"source": "fallback", "model": tile_model, "reason": "tile_generation_error"}
    except Exception:
        logger.exception("LL2 tile generation unexpected error; using template fallback")
        tiles = build_fallback_tiles(inputs=inputs)
        meta = {"source": "fallback", "model": tile_model, "reason": "unexpected_error"}
    out["ll2TileContent"] = tiles
    out["ll2TileContentMeta"] = meta
    return out


async def ingredient_analysis(*, body: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    scan_id = body.get("scanId")
    if not scan_id:
        raise ScannerApiError(400, "scanId is required")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    branded_ingredient_coll: AsyncIOMotorCollection = db[s.coll_branded_ingredient]
    ingredient_coll: AsyncIOMotorCollection = db[s.coll_ingredient]

    oid = ObjectId(str(scan_id)) if ObjectId.is_valid(str(scan_id)) else None
    if oid is None:
        raise ScannerApiError(400, "Invalid scanId")

    doc = await scan_coll.find_one({"_id": oid})
    if not doc:
        raise ScannerApiError(404, "Scan not found")

    ingredients = body.get("ingredients")
    if ingredients is None or (isinstance(ingredients, list) and len(ingredients) == 0):
        ingredients = doc.get("extractedIngredients") or []

    product_id_ref = _normalize_product_ref(body.get("productId"))
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=product_id_ref)
    if (ingredients is None or (isinstance(ingredients, list) and len(ingredients) == 0)) and product:
        ingredients = await _ingredients_from_product(
            product=product,
            branded_ingredients_coll=branded_ingredient_coll,
            ingredient_coll=ingredient_coll,
        )
    db_key_ingredients = await _key_ingredients_from_product(
        product=product,
        branded_ingredients_coll=branded_ingredient_coll,
        ingredient_coll=ingredient_coll,
    )

    specific_type = body.get("specificType")
    main_benefit = body.get("mainBenefit")
    if not specific_type and product:
        specific_type = _best_product_type(product)
    if not main_benefit and product:
        main_benefit = _best_main_benefit(product)
    language = body.get("langauge") or DEFAULT_LANGUAGE

    personalized = bool(body.get("personalizedMatching"))
    if personalized and user is None:
        raise ScannerApiError(401, "Please login to use personalized matching")
    user_id = _extract_user_id(user or {})
    details_doc = await user_details_coll.find_one({"userId": user_id}) if user_id is not None else None
    personalization_context = _build_personalization_context(details_doc or {}) if personalized else None

    if not personalized:
        cached = await _find_cached_non_personalized_analysis(
            scan_coll=scan_coll,
            product_ref=product_id_ref,
        )
        if cached:
            cached_analytic = dict(cached.get("analyticDetail") or {})
            cached_ingredients = cached.get("ingredients")
            if not isinstance(cached_ingredients, list):
                cached_ingredients = ingredients if isinstance(ingredients, list) else []
            await scan_coll.update_one(
                {"_id": oid},
                {
                    "$set": {
                        "analyticDetail": cached_analytic,
                        "ingredients": cached_ingredients,
                        "productId": product_id_ref,
                        "personalizedMatching": False,
                        "analysisCacheHit": True,
                        "analysisCacheSourceScanId": cached.get("_id"),
                        "ingredientAnalysisError": None,
                        "updatedAt": datetime.now(),
                    }
                },
            )
            profile_validation = None
            if user_id is not None:
                mode = _resolve_analysis_mode(
                    body=body,
                    product=product,
                    specific_type=specific_type,
                    main_benefit=main_benefit,
                )
                details_doc = details_doc or {}
                mode_state = await _upsert_validation_state(
                    user_details_coll=user_details_coll,
                    user_id=user_id,
                    mode=mode,
                    bump_scan_count=True,
                    details_doc=details_doc,
                )
                profile_validation = _build_prompt_payload(
                    mode=mode,
                    mode_state=mode_state,
                    details=details_doc,
                    force_prompt_if_missing=False,
                )
            return {
                "scanId": str(scan_id),
                "analyticDetail": cached_analytic,
                "ingredients": cached_ingredients,
                "profileValidation": profile_validation,
            }

    text_block = "\n".join(str(x) for x in ingredients) if isinstance(ingredients, list) else str(ingredients)
    user_msg = ingredient_analysis_user_message(
        ingredients_text=text_block,
        specific_type=specific_type,
        main_benefit=main_benefit,
        langauge=str(language),
        personalization_context=personalization_context,
    )

    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        parsed = extract_first_json_object(raw)
        analytic, ing_out = _normalize_analysis_payload(parsed, ingredients)
        analytic = _apply_db_key_ingredients(analytic, db_key_ingredients)
        analytic = _ensure_profile_match_insights(analytic, personalized=personalized)
        analytic = await _maybe_attach_ll2_tile_content(
            analytic=analytic,
            body=body,
            details_doc=details_doc,
            product=product,
            client=client,
            anthropic_model=s.anthropic_model,
        )
        await scan_coll.update_one(
            {"_id": oid},
            {
                "$set": {
                    "analyticDetail": analytic,
                    "ingredients": ing_out,
                    "productId": product_id_ref,
                    "personalizedMatching": personalized,
                    "analysisCacheHit": False,
                    "analysisCacheSourceScanId": None,
                    "ingredientAnalysisError": None,
                    "updatedAt": datetime.now(),
                }
            },
        )
        profile_validation = None
        if user_id is not None:
            mode = _resolve_analysis_mode(
                body=body,
                product=product,
                specific_type=specific_type,
                main_benefit=main_benefit,
            )
            details_doc = details_doc or {}
            mode_state = await _upsert_validation_state(
                user_details_coll=user_details_coll,
                user_id=user_id,
                mode=mode,
                bump_scan_count=True,
                details_doc=details_doc,
            )
            profile_validation = _build_prompt_payload(
                mode=mode,
                mode_state=mode_state,
                details=details_doc,
                force_prompt_if_missing=personalized,
            )
        return {
            "scanId": str(scan_id),
            "analyticDetail": analytic,
            "ingredients": ing_out,
            "profileValidation": profile_validation,
        }
    except Exception as e:
        await scan_coll.update_one(
            {"_id": oid},
            {"$set": {"ingredientAnalysisError": str(e), "updatedAt": datetime.now()}},
        )
        raise ScannerApiError(500, GENERIC_ANALYSIS_FAIL) from e


async def ingredient_analysis_from_text(
    *,
    body: dict[str, Any],
    user: dict[str, Any] | None,
) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    scan_detail_coll: AsyncIOMotorCollection = db[s.coll_scan_detail]
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    branded_ingredient_coll: AsyncIOMotorCollection = db[s.coll_branded_ingredient]
    ingredient_coll: AsyncIOMotorCollection = db[s.coll_ingredient]

    ingredients = body.get("ingredients")
    ingredients_text = body.get("ingredientsText")
    product_id_ref = _normalize_product_ref(body.get("productId"))
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=product_id_ref)
    product_ing_list = await _ingredients_from_product(
        product=product,
        branded_ingredients_coll=branded_ingredient_coll,
        ingredient_coll=ingredient_coll,
    )
    db_key_ingredients = await _key_ingredients_from_product(
        product=product,
        branded_ingredients_coll=branded_ingredient_coll,
        ingredient_coll=ingredient_coll,
    )
    if isinstance(ingredients, list) and ingredients:
        ing_list = [str(x).strip() for x in ingredients if str(x).strip()]
    elif product_ing_list:
        ing_list = product_ing_list
    elif isinstance(ingredients_text, str) and ingredients_text.strip():
        ing_list = _ingredient_list_from_text(ingredients_text)
    else:
        raise ScannerApiError(400, "ingredients or ingredientsText is required")

    personalized = bool(body.get("personalizedMatching"))
    if personalized and not user:
        raise ScannerApiError(401, "Please login to use personalized matching")

    personalization_context = None
    user_id = _extract_user_id(user or {})
    details = await user_details_coll.find_one({"userId": user_id}) if user_id is not None else None
    if personalized:
        if user_id is None:
            raise ScannerApiError(401, "Please login to use personalized matching")
        personalization_context = _build_personalization_context(details or {})

    now = datetime.now()
    scan_doc = {
        "userId": user_id,
        "firstName": (user or {}).get("firstName"),
        "lastName": (user or {}).get("lastName"),
        "userProfileUrl": (user or {}).get("profileUrl"),
        "extractedIngredients": ing_list,
        "scansLeft": None,
        "scanImageError": None,
        "ingredientAnalysisError": None,
        "sourceType": "text",
        "productId": product_id_ref,
        "createdAt": now,
        "updatedAt": now,
    }
    ins = await scan_coll.insert_one(scan_doc)
    scan_id = ins.inserted_id
    await scan_detail_coll.insert_one(
        {
            "scanAnalysisId": scan_id,
            "sourceType": "text",
            "extractedIngredients": ing_list,
            "createdAt": now,
            "updatedAt": now,
        }
    )

    if not personalized:
        cached = await _find_cached_non_personalized_analysis(
            scan_coll=scan_coll,
            product_ref=product_id_ref,
        )
        if cached:
            cached_analytic = dict(cached.get("analyticDetail") or {})
            cached_ingredients = cached.get("ingredients")
            if not isinstance(cached_ingredients, list):
                cached_ingredients = ing_list
            await scan_coll.update_one(
                {"_id": scan_id},
                {
                    "$set": {
                        "analyticDetail": cached_analytic,
                        "ingredients": cached_ingredients,
                        "personalizedMatching": False,
                        "analysisCacheHit": True,
                        "analysisCacheSourceScanId": cached.get("_id"),
                        "ingredientAnalysisError": None,
                        "updatedAt": datetime.now(),
                    }
                },
            )
            profile_validation = None
            if user_id is not None:
                mode = _resolve_analysis_mode(
                    body=body,
                    product=product,
                    specific_type=body.get("specificType"),
                    main_benefit=body.get("mainBenefit"),
                )
                mode_state = await _upsert_validation_state(
                    user_details_coll=user_details_coll,
                    user_id=user_id,
                    mode=mode,
                    bump_scan_count=True,
                    details_doc=details,
                )
                profile_validation = _build_prompt_payload(
                    mode=mode,
                    mode_state=mode_state,
                    details=details or {},
                    force_prompt_if_missing=False,
                )
            return {
                "scanId": str(scan_id),
                "analyticDetail": cached_analytic,
                "ingredients": cached_ingredients,
                "profileValidation": profile_validation,
            }

    specific_type = body.get("specificType")
    main_benefit = body.get("mainBenefit")
    if not specific_type and product:
        specific_type = _best_product_type(product)
    if not main_benefit and product:
        main_benefit = _best_main_benefit(product)
    language = body.get("langauge") or DEFAULT_LANGUAGE
    text_block = "\n".join(ing_list)
    user_msg = ingredient_analysis_user_message(
        ingredients_text=text_block,
        specific_type=specific_type,
        main_benefit=main_benefit,
        langauge=str(language),
        personalization_context=personalization_context,
    )

    client = AsyncAnthropic(api_key=s.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model=s.anthropic_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        parsed = extract_first_json_object(raw)
        analytic, ing_out = _normalize_analysis_payload(parsed, ing_list)
        analytic = _apply_db_key_ingredients(analytic, db_key_ingredients)
        analytic = _ensure_profile_match_insights(analytic, personalized=personalized)
        analytic = await _maybe_attach_ll2_tile_content(
            analytic=analytic,
            body=body,
            details_doc=details,
            product=product,
            client=client,
            anthropic_model=s.anthropic_model,
        )
        await scan_coll.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "analyticDetail": analytic,
                    "ingredients": ing_out,
                    "personalizedMatching": personalized,
                    "analysisCacheHit": False,
                    "analysisCacheSourceScanId": None,
                    "ingredientAnalysisError": None,
                    "updatedAt": datetime.now(),
                }
            },
        )
        profile_validation = None
        if user_id is not None:
            mode = _resolve_analysis_mode(
                body=body,
                product=product,
                specific_type=specific_type,
                main_benefit=main_benefit,
            )
            mode_state = await _upsert_validation_state(
                user_details_coll=user_details_coll,
                user_id=user_id,
                mode=mode,
                bump_scan_count=True,
                details_doc=details,
            )
            profile_validation = _build_prompt_payload(
                mode=mode,
                mode_state=mode_state,
                details=details or {},
                force_prompt_if_missing=personalized,
            )
        return {
            "scanId": str(scan_id),
            "analyticDetail": analytic,
            "ingredients": ing_out,
            "profileValidation": profile_validation,
        }
    except Exception as e:
        await scan_coll.update_one(
            {"_id": scan_id},
            {"$set": {"ingredientAnalysisError": str(e), "updatedAt": datetime.now()}},
        )
        raise ScannerApiError(500, GENERIC_ANALYSIS_FAIL) from e


async def submit_profile_validation(*, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Please login to submit profile validation")
    answers = body.get("answers")
    if not isinstance(answers, dict) or not answers:
        raise ScannerApiError(400, "answers object is required")
    mode = _normalize_mode(
        product_for=body.get("productFor"),
        specific_type=body.get("specificType"),
        main_benefit=body.get("mainBenefit"),
        mode_hint=body.get("mode"),
    )

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    details = await user_details_coll.find_one({"userId": user_id}) or {"userId": user_id}
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=body.get("productId"))

    resolved_mode = _resolve_analysis_mode(
        body=body,
        product=product,
        specific_type=body.get("specificType"),
        main_benefit=body.get("mainBenefit"),
    )
    llv = dict(details.get("labelLookerValidation") or {})
    mode_state = dict(
        llv.get(resolved_mode) or {"scanCount": 0, "promptRounds": 0, "attempts": {}, "finalValues": {}, "finalized": False}
    )
    mode_state, updates_for_details = _apply_answers_to_state(
        resolved_mode,
        mode_state,
        answers,
        details=details,
    )
    llv[resolved_mode] = mode_state

    set_doc = {"labelLookerValidation": llv, "updatedAt": datetime.now()}
    # keep skincare and haircare separate
    for k, v in updates_for_details.items():
        if k in ("skinType", "skinConcerns") and resolved_mode != "skincare":
            continue
        if k in ("lipType", "lipConcerns") and resolved_mode != "lipcare":
            continue
        if k in ("hairType", "hairConcerns") and resolved_mode != "haircare":
            continue
        set_doc[k] = v
    if "age" in updates_for_details:
        set_doc["age"] = updates_for_details["age"]
    if "gender" in updates_for_details:
        set_doc["gender"] = updates_for_details["gender"]

    merged_details = {**details, **set_doc}
    if not _has_missing_required(merged_details, resolved_mode, dict(mode_state.get("finalValues") or {})):
        mode_state["finalized"] = True
        llv[resolved_mode] = mode_state
        set_doc["labelLookerValidation"] = llv
    await user_details_coll.update_one({"userId": user_id}, {"$set": set_doc}, upsert=True)
    await _sync_profile_to_user_service(
        token=str(user.get("_label_looker_access_token") or "").strip() or None,
        updates=updates_for_details,
    )
    prompt = _build_prompt_payload(mode=resolved_mode, mode_state=mode_state, details=merged_details)
    return {
        "mode": resolved_mode,
        "finalized": bool(mode_state.get("finalized")),
        "finalValues": mode_state.get("finalValues") or {},
        "nextPrompt": prompt,
    }


async def profile_validation_status(*, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """
    Check whether required profile fields are available for this user/mode,
    and whether prompt should appear now based on scan cadence.
    """
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Please login to check profile validation status")

    requested_user_id = body.get("userId")
    if requested_user_id is not None and str(requested_user_id).strip() and str(requested_user_id) != str(user_id):
        raise ScannerApiError(403, "Forbidden: userId mismatch")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    user_details_coll: AsyncIOMotorCollection = db[s.coll_user_details]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    details = await user_details_coll.find_one({"userId": user_id}) or {"userId": user_id}
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=body.get("productId"))

    resolved_mode = _resolve_analysis_mode(
        body=body,
        product=product,
        specific_type=body.get("specificType"),
        main_benefit=body.get("mainBenefit"),
    )
    mode_state = await _upsert_validation_state(
        user_details_coll=user_details_coll,
        user_id=user_id,
        mode=resolved_mode,
        bump_scan_count=False,
        details_doc=details,
    )
    prompt = _build_prompt_payload(mode=resolved_mode, mode_state=mode_state, details=details)

    missing_fields: list[str] = []
    for f in _required_fields_for_mode(resolved_mode):
        val = _current_field_value(details, resolved_mode, f)
        if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
            missing_fields.append(f)

    return {
        "userId": str(user_id),
        "mode": resolved_mode,
        "requiredFields": _required_fields_for_mode(resolved_mode),
        "missingFields": missing_fields,
        "hasRequiredData": len(missing_fields) == 0,
        "scanCount": int(mode_state.get("scanCount") or 0),
        "finalized": bool(mode_state.get("finalized")),
        "shouldPromptNow": bool(prompt.get("shouldPrompt")),
        "prompt": prompt,
    }


async def put_feedback(*, body: dict[str, Any]) -> None:
    scan_id = body.get("scanId")
    if not scan_id:
        raise ScannerApiError(400, "scanId is required")
    rating = body.get("rating")
    feedback = body.get("feedback")
    if rating is not None and rating not in ("good", "okay", "bad"):
        raise ScannerApiError(400, "Invalid rating")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll = db[s.coll_scan_analysis]
    oid = ObjectId(str(scan_id)) if ObjectId.is_valid(str(scan_id)) else None
    if oid is None:
        raise ScannerApiError(400, "Invalid scanId")

    fields: dict[str, Any] = {"updatedAt": datetime.now()}
    if rating is not None:
        fields["rating"] = rating
    if feedback is not None:
        fields["feedback"] = feedback
    res = await scan_coll.update_one({"_id": oid}, {"$set": fields})
    if res.matched_count == 0:
        raise ScannerApiError(404, "Scan not found")


async def user_scan_by_id(*, scan_id: str, user: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch one scan for the authenticated end-user (owner only).
    """
    if not ObjectId.is_valid(scan_id):
        raise ScannerApiError(400, "Invalid scanId")
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Please login to fetch scan data")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    doc = await scan_coll.find_one({"_id": ObjectId(scan_id)})
    if not doc:
        raise ScannerApiError(404, "Scan not found")

    owner_id = doc.get("userId")
    if str(owner_id) != str(user_id):
        raise ScannerApiError(403, "Forbidden")
    out = dict(doc)

    product = await _fetch_product_by_id(products_coll=products_coll, product_id=out.get("productId"))
    base_url = s.skin_bb_base_url_norm
    if isinstance(product, dict):
        out["productName"] = product.get("productName") or product.get("name")
        thumb_raw = (
            product.get("thumbnail")
            or product.get("thumbnailUrl")
            or product.get("imageUrl")
            or product.get("productImage")
            or product.get("image")
        )
        out["productThumbnailId"] = str(thumb_raw) if thumb_raw is not None else None
        out["productThumbnailUrl"] = _resolve_image_url(thumb_raw, base_url=base_url)
        out["productThumbnail"] = out["productThumbnailUrl"] or out["productThumbnailId"]

    # For text scans there is no image upload; expose null explicitly for UI consistency.
    out.setdefault("scanImageUrl", None)
    out["displayImage"] = out.get("scanImageUrl") or out.get("productThumbnailUrl")

    # Always provide a computed scans-left value for current user session UI.
    profile_url = user.get("profileUrl") or out.get("userProfileUrl")
    count = await _count_scans_today(scan_coll, profile_url)
    out["scansLeft"] = max(0, totalScanIngedientPerDay - count)
    out["totalScanPerDay"] = totalScanIngedientPerDay
    return out


async def user_scan_list(*, user: dict[str, Any], skip: int = 0, limit: int = 20) -> list[dict[str, Any]]:
    """
    Fetch authenticated user's scans for history/refresh flows.
    """
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Please login to fetch scan data")

    s = get_label_looker_settings()
    from app.label_looker.db import get_scanner_db

    db = get_scanner_db()
    scan_coll: AsyncIOMotorCollection = db[s.coll_scan_analysis]
    products_coll: AsyncIOMotorCollection = db[s.coll_products]
    cursor = (
        scan_coll.find({"userId": user_id})
        .sort("createdAt", -1)
        .skip(max(0, int(skip)))
        .limit(max(1, min(int(limit), 100)))
    )
    rows = await cursor.to_list(length=max(1, min(int(limit), 100)))

    # One scan-left calculation for this user, then apply to each row.
    profile_url = user.get("profileUrl")
    count = await _count_scans_today(scan_coll, profile_url)
    scans_left = max(0, totalScanIngedientPerDay - count)
    base_url = s.skin_bb_base_url_norm

    product_ids: list[Any] = []
    for row in rows:
        pid = _normalize_product_ref(row.get("productId"))
        if pid is not None:
            product_ids.append(pid)
    product_map: dict[str, dict[str, Any]] = {}
    uniq_ids = list(dict.fromkeys(product_ids))
    if uniq_ids:
        cursor_p = products_coll.find({"_id": {"$in": uniq_ids}})
        async for p in cursor_p:
            product_map[str(p.get("_id"))] = p

    out_rows: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        out.setdefault("scanImageUrl", None)
        out["scansLeft"] = scans_left
        out["totalScanPerDay"] = totalScanIngedientPerDay
        pid = _normalize_product_ref(out.get("productId"))
        if pid is not None:
            pdoc = product_map.get(str(pid))
            if isinstance(pdoc, dict):
                out["productName"] = pdoc.get("productName") or pdoc.get("name")
                thumb_raw = (
                    pdoc.get("thumbnail")
                    or pdoc.get("thumbnailUrl")
                    or pdoc.get("imageUrl")
                    or pdoc.get("productImage")
                    or pdoc.get("image")
                )
                out["productThumbnailId"] = str(thumb_raw) if thumb_raw is not None else None
                out["productThumbnailUrl"] = _resolve_image_url(thumb_raw, base_url=base_url)
                out["productThumbnail"] = out["productThumbnailUrl"] or out["productThumbnailId"]
        out["displayImage"] = out.get("scanImageUrl") or out.get("productThumbnailUrl")
        out_rows.append(out)
    return out_rows
