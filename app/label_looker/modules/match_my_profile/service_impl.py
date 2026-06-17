from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from anthropic import AsyncAnthropic
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.engines import profile_match as profile_match_engines
from app.label_looker.engines.base_formula.context import resolve_runtime_context
from app.label_looker.engines.base_formula.derive import derive_base_formula_record
from app.label_looker.core.constants import totalScanIngedientPerDay
from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.services.common_flow import (
    count_scans_today,
    end_user_owns_scan_document,
    extract_user_id,
    require_end_user_owns_scan,
)
from app.label_looker.services.expected_benefit_options import (
    build_expected_benefit_options,
    validate_desired_benefits,
)
from app.label_looker.services.product_marketing_signals import (
    build_product_benefit_signals,
    resolve_product_tag_names,
)
from app.label_looker.services.tile_content_flow import generate_tiles_with_fallback
from app.label_looker.services.user_profile_flow import load_full_user_profile, merge_auth_user_details, resolve_users_collection_id, user_details_lookup_filter

logger = logging.getLogger(__name__)


def _extract_user_id(user: dict[str, Any]) -> Any:
    return extract_user_id(user)


def _has_score_request_body(body: dict[str, Any]) -> bool:
    if body.get("product_id") or body.get("productId"):
        return True
    desired = body.get("desiredBenefits") or body.get("desired_benefits")
    if isinstance(desired, list) and desired:
        return True
    if isinstance(desired, str) and desired.strip():
        return True
    return False


def _extract_analysis_scan_id(body: dict[str, Any]) -> str | None:
    for key in ("analysisScanId", "analysis_scan_id"):
        raw = body.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    scan_raw = body.get("scan_id") or body.get("scanId")
    if isinstance(scan_raw, str) and scan_raw.strip() and _has_score_request_body(body):
        return scan_raw.strip()
    return None


async def _load_linked_analysis_scan(
    *,
    scan_coll: AsyncIOMotorCollection,
    analysis_scan_id: str,
    user: dict[str, Any],
    user_id: Any,
    product_ref: Any,
) -> dict[str, Any] | None:
    if not ObjectId.is_valid(analysis_scan_id):
        raise ScannerApiError(400, "Invalid analysisScanId")
    oid = ObjectId(analysis_scan_id)
    doc = await scan_coll.find_one({"_id": oid})
    if not doc:
        raise ScannerApiError(404, "Analysis scan not found")
    require_end_user_owns_scan(doc=doc, user=user, user_id=user_id)
    linked_product = doc.get("productId")
    if linked_product is not None and product_ref is not None and str(linked_product) != str(product_ref):
        raise ScannerApiError(400, "analysisScanId does not match this product")
    return doc


def _effective_user_details_for_match(details: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    return merge_auth_user_details(details, user)


def _safe_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            for k in ("value", "label", "name"):
                val = item.get(k)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    break
    return list(dict.fromkeys(out))


def _as_string_list(raw: Any) -> list[str]:
    """Normalize patch payload list/string into a list of non-empty strings (empty list allowed)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        t = raw.strip()
        return [t] if t else []
    if isinstance(raw, list):
        return _safe_list(raw)
    return []


def _safe_scalar(raw: Any) -> str:
    if isinstance(raw, list):
        if not raw:
            return ""
        return _safe_scalar(raw[0])
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("value", "label", "name"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if raw is None:
        return ""
    return str(raw).strip()


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and len(value) == 0:
            continue
        return value
    return None


def _normalize_mode_for_match(*, body: dict[str, Any], product: dict[str, Any]) -> str:
    mode_hint = _safe_scalar(body.get("mode")).lower()
    if mode_hint in {"skincare", "haircare"}:
        return mode_hint

    product_type = _safe_scalar(product.get("productType")).lower()
    product_name = _safe_scalar(product.get("productName") or product.get("name")).lower()
    if "hair" in product_type or "scalp" in product_type or "hair" in product_name:
        return "haircare"
    if _product_list_values(product, "hairTypes", "hairType", "hairConcerns"):
        return "haircare"
    return "skincare"


def _extract_desired_benefits(*, body: dict[str, Any], details: dict[str, Any], mode: str) -> list[str]:
    body_benefits = _first_present(
        body.get("desiredBenefits"),
        body.get("desiredBenefit"),
        body.get("benefits"),
        body.get("skinGoals") if mode == "skincare" else body.get("hairGoals"),
        body.get("mainBenefit"),
    )
    if isinstance(body_benefits, list):
        cleaned = _safe_list(body_benefits)
        if cleaned:
            return cleaned
    if isinstance(body_benefits, str):
        text = body_benefits.strip()
        if text:
            return [text]

    db_fallback = details.get("skinGoals") if mode == "skincare" else details.get("hairGoals")
    return _safe_list(db_fallback)


def _extract_desired_benefits_from_body(*, body: dict[str, Any], mode: str) -> list[str]:
    _ = mode
    body_benefits = _first_present(
        body.get("desiredBenefits"),
        body.get("desiredBenefit"),
        body.get("benefits"),
        body.get("mainBenefit"),
    )
    if isinstance(body_benefits, list):
        return _safe_list(body_benefits)
    if isinstance(body_benefits, str):
        text = body_benefits.strip()
        return [text] if text else []
    return []


def _product_list_values(product: dict[str, Any] | None, *keys: str) -> list[str]:
    if not product:
        return []
    out: list[str] = []
    for key in keys:
        out.extend(_safe_list(product.get(key)))
    return list(dict.fromkeys(out))


async def _resolve_product_tag_names_for_match(
    *,
    product: dict[str, Any],
    db: Any,
) -> list[str]:
    tags_coll = db["product_tags"]
    return await resolve_product_tag_names(product=product, tags_coll=tags_coll)


def _normalize_product_ref(product_id: Any) -> Any | None:
    if product_id is None:
        return None
    if isinstance(product_id, ObjectId):
        return product_id
    pid = str(product_id).strip()
    if not pid:
        return None
    if ObjectId.is_valid(pid):
        return ObjectId(pid)
    return pid


def _normalize_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, dict):
        for key in ("$oid", "_id", "id"):
            raw = value.get(key)
            if isinstance(raw, ObjectId):
                return raw
            if isinstance(raw, str) and ObjectId.is_valid(raw):
                return ObjectId(raw)
        return None
    if isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return None


async def _resolve_ingredients_from_rows(
    *,
    rows: Any,
    branded_ingredients_coll: AsyncIOMotorCollection,
    ingredient_coll: AsyncIOMotorCollection,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    ref_ids: list[ObjectId] = []
    for idx, row in enumerate(rows, start=1):
        if isinstance(row, dict):
            try:
                position = int(row.get("position") or idx)
            except (TypeError, ValueError):
                position = idx
            name = str(row.get("inci_name") or "").strip() or str(row.get("ingredient_name") or "").strip() or str(row.get("name") or "").strip()
            if name:
                out.append({"position": position, "inci_name": name, "functions": row.get("functions") if isinstance(row.get("functions"), list) else [], "addresses": row.get("addresses") if isinstance(row.get("addresses"), list) else []})
                continue
        oid = _normalize_object_id(row)
        if oid is not None:
            ref_ids.append(oid)

    dedup_ref_ids = list(dict.fromkeys(ref_ids))
    if not dedup_ref_ids:
        return out
    resolved: dict[ObjectId, str] = {}
    cursor = branded_ingredients_coll.find({"_id": {"$in": dedup_ref_ids}}, {"ingredient_name": 1, "name": 1, "inci_name": 1})
    async for doc in cursor:
        name = str(doc.get("ingredient_name") or "").strip() or str(doc.get("name") or "").strip() or str(doc.get("inci_name") or "").strip()
        if name:
            resolved[doc["_id"]] = name
    unresolved = [oid for oid in dedup_ref_ids if oid not in resolved]
    if unresolved:
        cursor = ingredient_coll.find({"_id": {"$in": unresolved}}, {"name": 1, "ingredient_name": 1, "inci_name": 1})
        async for doc in cursor:
            name = str(doc.get("name") or "").strip() or str(doc.get("ingredient_name") or "").strip() or str(doc.get("inci_name") or "").strip()
            if name:
                resolved[doc["_id"]] = name
    existing_names = {str(row.get("inci_name") or "").strip().lower() for row in out}
    for pos, oid in enumerate(dedup_ref_ids, start=1):
        name = resolved.get(oid)
        if not name or name.lower() in existing_names:
            continue
        out.append({"position": pos, "inci_name": name, "functions": [], "addresses": []})
        existing_names.add(name.lower())
    return out


def _stored_observation_ids(doc: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    raw = doc.get("triggered_observations")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                oid = str(item.get("id") or "").strip()
                if oid:
                    ids.append(oid)
            elif isinstance(item, str) and item.strip():
                ids.append(item.strip())
    if not ids:
        legacy_ids = doc.get("triggered_obs")
        if isinstance(legacy_ids, list):
            ids = [str(sid).strip() for sid in legacy_ids if isinstance(sid, str) and str(sid).strip()]
    return ids


def _observation_context_from_scan_doc(doc: dict[str, Any]) -> dict[str, Any]:
    breakdown = doc.get("engine_breakdown") if isinstance(doc.get("engine_breakdown"), dict) else {}
    suitability = breakdown.get("suitability") if isinstance(breakdown.get("suitability"), dict) else {}
    safety = breakdown.get("safety") if isinstance(breakdown.get("safety"), dict) else {"severity": "clear", "triggers": []}
    unmet_needs = suitability.get("unmet_needs") if isinstance(suitability.get("unmet_needs"), list) else []
    return {
        "state": str(doc.get("state") or suitability.get("band") or suitability.get("state") or "low"),
        "safety": safety,
        "unmet_needs": [str(x) for x in unmet_needs if str(x).strip()],
    }


def _stored_triggered_observations(doc: dict[str, Any]) -> list[Any]:
    """Rehydrate observation objects; legacy rows may only have string ids in ``triggered_obs``."""
    raw = doc.get("triggered_observations")
    if isinstance(raw, list) and raw and all(
        isinstance(item, dict) and str(item.get("editorial_text") or "").strip() for item in raw
    ):
        return raw

    ids = _stored_observation_ids(doc)
    if not ids:
        return []

    ctx = _observation_context_from_scan_doc(doc)
    return profile_match_engines.resolve_observations_by_ids(
        ids=ids,
        safety=ctx["safety"],
        unmet_needs=ctx["unmet_needs"],
        product_primary="",
        claims=[],
        base_formula=None,
        user_flags=None,
    )


def _build_match_product(product: dict[str, Any]) -> dict[str, Any]:
    ingredients = product.get("ingredients")
    out_ingredients: list[dict[str, Any]] = []
    if isinstance(ingredients, list):
        for idx, row in enumerate(ingredients, start=1):
            if not isinstance(row, dict):
                continue
            name = str(row.get("inci_name") or "").strip() or str(row.get("ingredient_name") or "").strip() or str(row.get("name") or "").strip()
            if not name:
                continue
            position_raw = row.get("position")
            try:
                position = int(position_raw)
            except (TypeError, ValueError):
                position = idx
            out_ingredients.append({"position": position, "inci_name": name, "functions": row.get("functions") if isinstance(row.get("functions"), list) else [], "addresses": row.get("addresses") if isinstance(row.get("addresses"), list) else []})
    key_ingredients = product.get("keyIngredients")
    out_key_ingredients: list[dict[str, Any]] = []
    if isinstance(key_ingredients, list):
        for idx, row in enumerate(key_ingredients, start=1):
            if not isinstance(row, dict):
                continue
            name = str(row.get("inci_name") or "").strip() or str(row.get("ingredient_name") or "").strip() or str(row.get("name") or "").strip()
            if not name:
                continue
            position_raw = row.get("position")
            try:
                position = int(position_raw)
            except (TypeError, ValueError):
                position = idx
            out_key_ingredients.append({"position": position, "inci_name": name, "functions": row.get("functions") if isinstance(row.get("functions"), list) else [], "addresses": row.get("addresses") if isinstance(row.get("addresses"), list) else []})
    return {
        "brand": str(product.get("brandName") or "SkinBB").strip() or "SkinBB",
        "name": str(product.get("productName") or product.get("name") or "Product").strip() or "Product",
        "category": str(product.get("productType") or "skincare").strip() or "skincare",
        "declared_for_skin_types": [x.lower() for x in _product_list_values(product, "skinTypes", "skinType")],
        "claims": _product_list_values(product, "benefit", "claims"),
        "ingredients": out_ingredients,
        "key_ingredients": out_key_ingredients,
    }


def _derive_base_formula_from_product(product: dict[str, Any], tile_product: dict[str, Any]) -> dict[str, Any]:
    return derive_base_formula_record(product=product, tile_product=tile_product)


def _build_cta(*, state: str, product_price: Any) -> dict[str, Any]:
    price_label = f"₹{int(product_price)}" if isinstance(product_price, (int, float)) else "Add to cart"
    if state in ("great", "good"):
        return {"primary": {"action": "add_to_cart", "label": f"Add to cart - {price_label}"}, "secondary": {"action": "save_for_later", "label": "Save for later"}}
    if state == "low":
        return {"primary": {"action": "explore_better_matches", "label": "Explore better matches"}, "secondary": {"action": "still_add_this", "label": "Still add this"}}
    return {"primary": {"action": "explore_safer", "label": "See safer options"}, "secondary": {"action": "go_back", "label": "Go back"}}


async def _count_scans_today(coll: AsyncIOMotorCollection, profile_url: str | None) -> int:
    return await count_scans_today(coll, profile_url)


async def _find_latest_product_analysis_detail(*, scan_coll: AsyncIOMotorCollection, product_ref: Any | None) -> dict[str, Any] | None:
    if product_ref is None:
        return None
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    from app.label_looker.services.product_analysis_store import find_product_analysis

    db = get_scanner_db()
    stored = await find_product_analysis(coll=db[s.coll_product_analysis], product_ref=product_ref)
    if stored and isinstance(stored.get("analyticDetail"), dict):
        return stored.get("analyticDetail")
    doc = await scan_coll.find_one(
        {
            "productId": product_ref,
            "analyticDetail": {"$exists": True, "$ne": None},
            "ingredientAnalysisError": None,
        },
        sort=[("updatedAt", -1)],
    )
    if not doc:
        return None
    analytic = doc.get("analyticDetail")
    return analytic if isinstance(analytic, dict) else None


async def get_profile(*, user: dict[str, Any], product_id: str | None = None) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    from app.label_looker.modules.product_analysis.analysis_service_impl import (
        _fetch_product_by_id,
        _resolve_analysis_mode,
    )
    from app.label_looker.services.profile_form import assess_profile_completeness, build_profile_form_values

    db = get_scanner_db()
    user_details_coll = db[s.coll_user_details]
    scan_coll = db[s.coll_scan_analysis]
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    details_raw = await load_full_user_profile(user_id=user_id, user=user)
    details = details_raw
    scans_used = await _count_scans_today(scan_coll, user.get("profileUrl"))

    mode = "skincare"
    if product_id and str(product_id).strip():
        products_coll = db[s.coll_products]
        product = await _fetch_product_by_id(products_coll=products_coll, product_id=product_id.strip())
        mode = _resolve_analysis_mode(body={}, product=product, specific_type=None, main_benefit=None)

    completeness = assess_profile_completeness(details=details, auth_user=user, mode=mode)
    form_values = build_profile_form_values(details=details, auth_user=user)

    profile = {
        "id": str(user_id),
        "name": details.get("name") or user.get("firstName"),
        "age": completeness["form"]["flat"].get("age") or details.get("age"),
        "gender": completeness["form"]["flat"].get("gender") or details.get("gender"),
        "category_profiles": {
            "skin": {
                "type": completeness["form"]["skin"].get("skinType") or details.get("skinType"),
                "concerns": _safe_list(completeness["form"]["skin"].get("skinConcerns") or details.get("skinConcerns")),
                "benefits_wanted": _safe_list(completeness["form"]["skin"].get("skinGoals") or details.get("skinGoals")),
            },
            "hair": {
                "type": completeness["form"]["hair"].get("hairType") or details.get("hairType"),
                "concerns": _safe_list(completeness["form"]["hair"].get("hairConcerns") or details.get("hairConcerns")),
                "benefits_wanted": _safe_list(completeness["form"]["hair"].get("hairGoals") or details.get("hairGoals")),
            },
        },
        "safety": {
            "life_stages": _safe_list(details.get("lifeStages") or details.get("life_stages")),
            "allergies": _safe_list(details.get("allergies")),
            "conditions": _safe_list(details.get("conditions")),
            "medications": _safe_list(details.get("medications")),
        },
        "credits": {"free_used": scans_used, "free_limit": totalScanIngedientPerDay, "paid_remaining": 0},
        "form": form_values,
        "fieldStatus": completeness["fieldStatus"],
        "missingFields": completeness["missingFields"],
        "missingFieldDetails": completeness["missingFieldDetails"],
        "highlightFields": completeness["highlightFields"],
        "hasRequiredForScan": completeness["hasRequiredForScan"],
        "requiredFieldsForScan": completeness["requiredFieldsForScan"],
        "scanMode": mode,
    }
    profile["categoryProfiles"] = profile["category_profiles"]
    profile["benefitsWanted"] = {
        "skin": profile["category_profiles"]["skin"]["benefits_wanted"],
        "hair": profile["category_profiles"]["hair"]["benefits_wanted"],
    }
    return profile


async def patch_profile(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    from app.label_looker.services.profile_form import profile_updates_from_form_body

    db = get_scanner_db()
    user_details_coll = db[s.coll_user_details]
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    updates: dict[str, Any] = {"updatedAt": datetime.now()}
    form_updates = profile_updates_from_form_body(body)
    updates.update(form_updates)

    if "name" in body:
        updates["name"] = body.get("name")
    if "age" in body and "age" not in form_updates:
        updates["age"] = body.get("age")
    if "gender" in body and "gender" not in form_updates:
        updates["gender"] = body.get("gender")
    category_profiles = body.get("category_profiles") or body.get("categoryProfiles")
    if isinstance(category_profiles, dict):
        skin = category_profiles.get("skin")
        if isinstance(skin, dict):
            if "type" in skin and "skinType" not in updates:
                updates["skinType"] = skin.get("type")
            if "concerns" in skin and "skinConcerns" not in updates:
                updates["skinConcerns"] = _as_string_list(skin.get("concerns"))
            elif "skinConcerns" in skin and "skinConcerns" not in updates:
                updates["skinConcerns"] = _as_string_list(skin.get("skinConcerns"))
            if "benefits_wanted" in skin and "skinGoals" not in updates:
                updates["skinGoals"] = _as_string_list(skin.get("benefits_wanted"))
            elif "benefitsWanted" in skin and "skinGoals" not in updates:
                updates["skinGoals"] = _as_string_list(skin.get("benefitsWanted"))
            elif "skinGoals" in skin and "skinGoals" not in updates:
                updates["skinGoals"] = _as_string_list(skin.get("skinGoals"))
        hair = category_profiles.get("hair")
        if isinstance(hair, dict):
            if "type" in hair and "hairType" not in updates:
                updates["hairType"] = hair.get("type")
            if "concerns" in hair and "hairConcerns" not in updates:
                updates["hairConcerns"] = _as_string_list(hair.get("concerns"))
            elif "hairConcerns" in hair and "hairConcerns" not in updates:
                updates["hairConcerns"] = _as_string_list(hair.get("hairConcerns"))
            if "benefits_wanted" in hair and "hairGoals" not in updates:
                updates["hairGoals"] = _as_string_list(hair.get("benefits_wanted"))
            elif "benefitsWanted" in hair and "hairGoals" not in updates:
                updates["hairGoals"] = _as_string_list(hair.get("benefitsWanted"))
            elif "hairGoals" in hair and "hairGoals" not in updates:
                updates["hairGoals"] = _as_string_list(hair.get("hairGoals"))
    safety = body.get("safety")
    if isinstance(safety, dict):
        if "life_stages" in safety or "lifeStages" in safety:
            updates["lifeStages"] = _first_present(safety.get("life_stages"), safety.get("lifeStages"))
        if "allergies" in safety:
            updates["allergies"] = safety.get("allergies")
        if "conditions" in safety:
            updates["conditions"] = safety.get("conditions")
        if "medications" in safety:
            updates["medications"] = safety.get("medications")
    product_id = body.get("productId") or body.get("product_id")
    users_coll = db[s.coll_user]
    mongo_user_id = await resolve_users_collection_id(users_coll=users_coll, user_id=user_id, auth_user=user)
    user_details_key = user_details_lookup_filter(user_id, mongo_user_id=mongo_user_id)
    set_doc = dict(updates)
    if mongo_user_id is not None:
        set_doc["userId"] = mongo_user_id
    elif user_id is not None:
        set_doc["userId"] = user_id
    await user_details_coll.update_one(
        user_details_key,
        {"$set": set_doc},
        upsert=True,
    )
    return await get_profile(user=user, product_id=str(product_id).strip() if product_id else None)


async def score_product(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    requested_scan_id = body.get("scan_id") or body.get("scanId")
    if isinstance(requested_scan_id, str) and requested_scan_id.strip() and not _has_score_request_body(body):
        return await get_scan_result(user=user, scan_id=requested_scan_id.strip())
    return await _score_product_impl(user=user, body=body)


async def _score_product_impl(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    product_id = body.get("product_id") or body.get("productId")
    if not product_id:
        raise ScannerApiError(400, "product_id is required")
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    db = get_scanner_db()
    products_coll = db[s.coll_products]
    branded_ingredient_coll = db[s.coll_branded_ingredient]
    ingredient_coll = db[s.coll_ingredient]
    user_details_coll = db[s.coll_user_details]
    scan_coll = db[s.coll_scan_analysis]
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    product_ref = _normalize_product_ref(product_id)
    analysis_scan_id = _extract_analysis_scan_id(body)
    linked_analysis = None
    if analysis_scan_id:
        linked_analysis = await _load_linked_analysis_scan(
            scan_coll=scan_coll,
            analysis_scan_id=analysis_scan_id,
            user=user,
            user_id=user_id,
            product_ref=product_ref,
        )
    scans_used_before = await _count_scans_today(scan_coll, user.get("profileUrl"))
    if linked_analysis is None and scans_used_before >= totalScanIngedientPerDay:
        raise ScannerApiError(402, "insufficient_credits")
    details_raw = await load_full_user_profile(user_id=user_id, user=user)
    details = details_raw
    product = await products_coll.find_one({"_id": product_ref})
    if not product:
        raise ScannerApiError(404, "Product not found")
    tag_names = await _resolve_product_tag_names_for_match(product=product, db=db)
    mode = _normalize_mode_for_match(body=body, product=product)
    if mode == "haircare":
        type_value = _safe_scalar(_first_present(details.get("hairType"), body.get("hairType")))
        concerns = _safe_list(_first_present(details.get("hairConcerns"), body.get("hairConcerns")))
        declared_types = _product_list_values(product, "hairTypes", "hairType")
    else:
        type_value = _safe_scalar(_first_present(details.get("skinType"), body.get("skinType")))
        concerns = _safe_list(_first_present(details.get("skinConcerns"), body.get("skinConcerns")))
        declared_types = _product_list_values(product, "skinTypes", "skinType")
    age = _first_present(details.get("age"), body.get("age"))
    gender = _safe_scalar(_first_present(details.get("gender"), body.get("gender")))
    benefits_from_body = _extract_desired_benefits_from_body(body=body, mode=mode)
    benefit_options = build_expected_benefit_options(product=product, mode=mode, tag_names=tag_names)
    life_stages = _safe_list(details.get("lifeStages") or details.get("life_stages"))
    conditions = _safe_list(details.get("conditions"))

    missing_profile_fields: list[str] = []
    if age is None:
        missing_profile_fields.append("age")
    if not gender:
        missing_profile_fields.append("gender")
    if not type_value:
        missing_profile_fields.append("hairType" if mode == "haircare" else "skinType")
    if not concerns:
        missing_profile_fields.append("hairConcerns" if mode == "haircare" else "skinConcerns")
    missing_inputs: list[dict[str, Any]] = []
    if missing_profile_fields:
        missing_inputs.append(
            {
                "source": "profile",
                "fields": missing_profile_fields,
                "rule": "Complete profile once (age, gender, type, concerns) before matching.",
            }
        )
    if not benefits_from_body:
        missing_inputs.append(
            {
                "source": "request",
                "fields": ["desiredBenefits"],
                "rule": "Select expected benefits for this product on every scan.",
                "expectedBenefitOptions": benefit_options.get("expectedBenefitOptions"),
                "selectionRules": benefit_options.get("selectionRules"),
            }
        )
    if missing_inputs:
        from app.label_looker.services.profile_form import assess_profile_completeness

        completeness = assess_profile_completeness(details=details, auth_user=user, mode=mode)
        for block in missing_inputs:
            if block.get("source") == "profile":
                block["highlightFields"] = completeness["highlightFields"]
                block["missingFieldDetails"] = completeness["missingFieldDetails"]
                block["form"] = completeness["form"]
        raise ScannerApiError(400, f"Missing required match input(s) for {mode}", errors=missing_inputs)

    benefits = validate_desired_benefits(
        desired=benefits_from_body,
        options_payload=benefit_options,
        product=product,
        tag_names=tag_names,
    )

    tile_product = _build_match_product(product)
    tile_product["declared_for_skin_types"] = [x.lower().strip() for x in declared_types if str(x).strip()]
    if isinstance(product.get("keyIngredients"), list):
        tile_product["key_ingredients"] = await _resolve_ingredients_from_rows(rows=product.get("keyIngredients"), branded_ingredients_coll=branded_ingredient_coll, ingredient_coll=ingredient_coll)
    if isinstance(product.get("ingredients"), list):
        tile_product["ingredients"] = await _resolve_ingredients_from_rows(rows=product.get("ingredients"), branded_ingredients_coll=branded_ingredient_coll, ingredient_coll=ingredient_coll)
    runtime_context = resolve_runtime_context(
        {"id": str(user_id), "skin_type": type_value.lower(), "age": age if isinstance(age, int) else None, "concerns": concerns, "benefits": benefits, "self_declared_flags": conditions, "life_stages": life_stages},
        _safe_scalar(body.get("pin_code") or body.get("pinCode")) or None,
        datetime.now(),
    )
    base_formula = _derive_base_formula_from_product(product, tile_product)
    safety = profile_match_engines.evaluate_safety(age=age if isinstance(age, int) else None, life_stages=life_stages, conditions=conditions, key_ingredients=tile_product["key_ingredients"])
    state = "gate" if safety["severity"] in ("block", "hard") else None
    if state == "gate":
        scoring: dict[str, Any] = {"state": "gate", "score": None, "band": "gate", "breakdown": [], "unmet_needs": concerns[:1]}
    else:
        suitability = profile_match_engines.evaluate_suitability(
            skin_type=type_value.lower(),
            concerns=concerns,
            benefits=benefits,
            declared_types=declared_types,
            product_primary=str(product.get("primaryConcern") or ""),
            product_benefits=build_product_benefit_signals(
                product=product,
                tile_product=tile_product,
                tag_names=tag_names,
                mode=mode,
            ),
            runtime_context=runtime_context,
            base_formula=base_formula,
            safety_severity=str(safety.get("severity") or "clear"),
            mode=mode,
        )
        state = suitability["band"]
        scoring = {
            "state": state,
            "score": suitability["final_score"],
            "band": suitability["band"],
            "ceiling_applied": suitability["type_ceiling"],
            "breakdown": suitability["breakdown"],
            "unmet_needs": suitability["unmet_needs"],
            "unmet_profile_concerns": suitability.get("unmet_profile_concerns", []),
            "unmatched_desired_benefits": suitability.get("unmatched_desired_benefits", []),
            "matched_desired_benefits": suitability.get("matched_desired_benefits", []),
            "scored_for": concerns,
            "desired_benefits": benefits,
            "base_formula_score": suitability.get("base_formula_score"),
            "overrides_applied": (suitability.get("override_result") or {}).get("overrides_applied", []),
            "fit_axes": suitability.get("fit_axes", []),
            "works_for_user": suitability.get("works_for_user"),
        }

    tile_user = {"mode": mode, "age": age if age is not None else "—", "gender": gender or "—", "skin_type": type_value.lower() if type_value else "—", "hair_type": type_value.lower() if mode == "haircare" and type_value else "—", "concerns": concerns, "benefits": benefits, "life_stages": life_stages}
    profile_context = {"mode": mode, "age": age, "gender": gender, "type": type_value, "concerns": concerns, "expected_benefits": benefits}
    observations = profile_match_engines.evaluate_observations(
        state=state or "low",
        safety=safety,
        unmet_needs=scoring.get("unmet_needs", []),
        product_primary=str(product.get("primaryConcern") or ""),
        claims=_product_list_values(product, "claims", "benefit"),
        base_formula=base_formula,
        user_flags=runtime_context.get("flags"),
        mode=mode,
    )
    tile_inputs = {"user": tile_user, "product": tile_product, "scoring": scoring, "observations": observations}
    tiles_meta: dict[str, Any] = {"source": "claude", "model": s.anthropic_model}
    if state == "gate":
        tiles = {"verdict": "Safety flag detected for your profile and this formula.", "works": "This product may still be effective for some users, but your profile triggered a safety gate.", "falls_short": safety["triggers"][0]["explanation"] if safety["triggers"] else "A safety concern was detected.", "falls_short_tone": "caution", "worth_knowing": "Review safer alternatives that target the same concerns.", "covered_message": None}
        tiles_meta = {"source": "gate-template", "model": None}
    else:
        client = AsyncAnthropic(api_key=s.anthropic_api_key)
        tiles, tiles_meta = await generate_tiles_with_fallback(inputs=tile_inputs, client=client, model=s.anthropic_model, context="profile_match")

    now = datetime.now()
    doc = {
        "userId": user_id,
        "userProfileUrl": user.get("profileUrl"),
        "firstName": user.get("firstName"),
        "lastName": user.get("lastName"),
        "productId": product_ref,
        "state": state,
        "score": scoring.get("score"),
        "band": scoring.get("band"),
        "engine_breakdown": {"safety": safety, "suitability": scoring},
        "generation_meta": tiles_meta,
        "profile_context": profile_context,
        "tile_content": tiles,
        "post_scan_action": None,
        "feedback": {"sentiment": None, "category": None, "note": None, "submittedAt": None},
        "triggered_obs": [str(x.get("id")) for x in observations if x.get("id")],
        "triggered_observations": observations,
        "scanImageError": None,
        "ingredientAnalysisError": None,
        "scanPhase": "complete",
        "updatedAt": now,
    }
    if linked_analysis is not None:
        scan_id = linked_analysis["_id"]
        await scan_coll.update_one({"_id": scan_id}, {"$set": doc})
    else:
        doc["createdAt"] = now
        doc["scanPhase"] = "match_only"
        ins = await scan_coll.insert_one(doc)
        scan_id = ins.inserted_id
    scans_used = await _count_scans_today(scan_coll, user.get("profileUrl"))
    cta = _build_cta(state=state or "low", product_price=product.get("price"))
    if linked_analysis and isinstance(linked_analysis.get("analyticDetail"), dict):
        legacy_analytic_detail = linked_analysis["analyticDetail"]
    else:
        legacy_analytic_detail = await _find_latest_product_analysis_detail(scan_coll=scan_coll, product_ref=product_ref)
    analysis_ingredients = (
        linked_analysis.get("ingredients")
        if linked_analysis and isinstance(linked_analysis.get("ingredients"), list)
        else tile_product.get("ingredients", [])
    )
    band_label_map = {
        "great": "Great Match",
        "good": "Good Match",
        "mixed": "Mixed Match",
        "low": "Low Match",
        "gate": "Gate",
    }
    match_result: dict[str, Any] = {
        "scan_id": str(scan_id),
        "state": state,
        "band": scoring.get("band"),
        "band_label": band_label_map.get(str(scoring.get("band")), "Match"),
        "score": scoring.get("score"),
        "ceiling_applied": scoring.get("ceiling_applied"),
        "works_for_user": scoring.get("works_for_user"),
        "fit_axes": scoring.get("fit_axes", []),
        "tiles": tiles,
        "breakdown": scoring.get("breakdown", []),
        "unmet_needs": scoring.get("unmet_needs", []),
        "unmet_profile_concerns": scoring.get("unmet_profile_concerns", []),
        "unmatched_desired_benefits": scoring.get("unmatched_desired_benefits", []),
        "matched_desired_benefits": scoring.get("matched_desired_benefits", []),
        "safety": safety,
        "scored_for": concerns,
        "desired_benefits": benefits,
        "profile_context": profile_context,
        "triggered_observations": observations,
        "base_formula": scoring.get("base_formula_score"),
        "overrides_applied": scoring.get("overrides_applied", []),
        "cta": cta,
        "full_analysis": {"ingredients": analysis_ingredients, "key_ingredients": tile_product.get("key_ingredients", []), "claims_checked": tile_product.get("claims", []), "legacy_analytic_detail": legacy_analytic_detail},
        "credits_remaining": {"free": max(0, totalScanIngedientPerDay - scans_used), "paid": 0},
        "position_reference": "Ingredient positions refer to INCI order in the formula list (lower number = higher concentration zone).",
        "expected_benefit_options": benefit_options.get("expectedBenefitOptions"),
        "selection_rules": benefit_options.get("selectionRules"),
        "mode": mode,
    }
    from app.label_looker.services.match_response import build_match_api_payload

    response = build_match_api_payload(match_result)
    response["result"]["expected_benefit_options"] = match_result["expected_benefit_options"]
    response["result"]["selection_rules"] = match_result["selection_rules"]
    response["expectedBenefitOptions"] = match_result["expected_benefit_options"]
    response["selectionRules"] = match_result["selection_rules"]
    if state == "gate":
        gate_severity = "block" if safety["severity"] == "block" else "hard"
        gate_payload = {
            "title": "Not Recommended" if gate_severity == "block" else "Proceed with caution",
            "summary": (safety["triggers"][0]["explanation"] if safety["triggers"] else "Safety concern detected."),
            "evidence": (safety["triggers"][0]["explanation"] if safety["triggers"] else "Rule-based safety gate triggered."),
            "label_vs_formula": "This safety call is based on profile-to-ingredient checks, not just marketing claims.",
            "gate_severity": gate_severity,
            "override_allowed": gate_severity == "hard",
        }
        response["gate"] = gate_payload
        response["result"]["gate"] = gate_payload
    return response


async def submit_feedback(*, user: dict[str, Any], scan_id: str, body: dict[str, Any]) -> dict[str, Any]:
    if not ObjectId.is_valid(scan_id):
        raise ScannerApiError(400, "Invalid scan_id")
    sentiment = body.get("sentiment")
    if sentiment not in ("up", "down"):
        raise ScannerApiError(400, "sentiment must be 'up' or 'down'")
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    db = get_scanner_db()
    scan_coll = db[s.coll_scan_analysis]
    doc = await scan_coll.find_one({"_id": ObjectId(scan_id)})
    if not doc:
        raise ScannerApiError(404, "Scan not found")
    require_end_user_owns_scan(doc=doc, user=user, user_id=user_id)
    payload = {"sentiment": sentiment, "category": body.get("category"), "note": body.get("note"), "submittedAt": datetime.now()}
    post_scan_action = body.get("post_scan_action") or body.get("postScanAction")
    res = await scan_coll.update_one({"_id": ObjectId(scan_id)}, {"$set": {"feedback": payload, "post_scan_action": post_scan_action, "updatedAt": datetime.now()}})
    if res.matched_count == 0:
        raise ScannerApiError(404, "Scan not found")
    return {"scan_id": scan_id, "scanId": scan_id, "feedback": payload, "post_scan_action": post_scan_action, "postScanAction": post_scan_action}


async def get_scan_result(*, user: dict[str, Any], scan_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(scan_id):
        raise ScannerApiError(400, "Invalid scan_id")
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    db = get_scanner_db()
    scan_coll = db[s.coll_scan_analysis]
    oid = ObjectId(scan_id)
    doc = await scan_coll.find_one({"_id": oid})
    if not doc:
        raise ScannerApiError(404, "Scan not found")
    if not end_user_owns_scan_document(doc, user, user_id):
        raise ScannerApiError(403, "Forbidden")
    suitability = doc.get("engine_breakdown", {}).get("suitability", {})
    safety = doc.get("engine_breakdown", {}).get("safety", {}) if isinstance(doc.get("engine_breakdown"), dict) else {}
    scans_used = await _count_scans_today(scan_coll, user.get("profileUrl") or doc.get("userProfileUrl"))
    band_label_map = {
        "great": "Great Match",
        "good": "Good Match",
        "mixed": "Mixed Match",
        "low": "Low Match",
        "gate": "Gate",
    }
    match_result: dict[str, Any] = {
        "scan_id": scan_id,
        "state": doc.get("state"),
        "band": doc.get("band"),
        "band_label": band_label_map.get(str(doc.get("band")), "Match"),
        "score": doc.get("score"),
        "ceiling_applied": suitability.get("ceiling_applied"),
        "works_for_user": suitability.get("works_for_user"),
        "fit_axes": suitability.get("fit_axes", []),
        "tiles": doc.get("tile_content") if isinstance(doc.get("tile_content"), dict) else {},
        "breakdown": suitability.get("breakdown", []),
        "unmet_needs": suitability.get("unmet_needs", []),
        "unmet_profile_concerns": suitability.get("unmet_profile_concerns", []),
        "unmatched_desired_benefits": suitability.get("unmatched_desired_benefits", []),
        "matched_desired_benefits": suitability.get("matched_desired_benefits", []),
        "safety": safety if isinstance(safety, dict) else {},
        "scored_for": suitability.get("scored_for", []),
        "desired_benefits": suitability.get("desired_benefits", []),
        "profile_context": doc.get("profile_context", {}),
        "triggered_observations": _stored_triggered_observations(doc),
        "base_formula": suitability.get("base_formula_score"),
        "overrides_applied": suitability.get("overrides_applied", []),
        "feedback": doc.get("feedback") if isinstance(doc.get("feedback"), dict) else None,
        "post_scan_action": doc.get("post_scan_action"),
        "credits_remaining": {"free": max(0, totalScanIngedientPerDay - scans_used), "paid": 0},
        "position_reference": "Ingredient positions refer to INCI order in the formula list (lower number = higher concentration zone).",
    }
    from app.label_looker.services.match_response import build_match_api_payload

    return build_match_api_payload(match_result)

