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
from app.label_looker.services.common_flow import count_scans_today, end_user_owns_scan_document, extract_user_id
from app.label_looker.services.tile_content_flow import generate_tiles_with_fallback

logger = logging.getLogger(__name__)


def _extract_user_id(user: dict[str, Any]) -> Any:
    return extract_user_id(user)


def _effective_user_details_for_match(details: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """
    Label Looker persists profile edits in Mongo `user_details`. For new users that row is empty
    while Node `user-details` (auth) already returns age / gender / skin / hair fields — merge so
    GET /profile and scoring see the same facts as Node.
    """
    merged = dict(details or {})
    scalar_keys = ("age", "gender", "skinType", "hairType")
    for k in scalar_keys:
        v = merged.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            uval = user.get(k)
            if uval is not None and (not isinstance(uval, str) or str(uval).strip()):
                merged[k] = uval
    list_keys = ("skinConcerns", "skinGoals", "hairConcerns", "hairGoals")
    for k in list_keys:
        cur = merged.get(k)
        if cur is None:
            uval = user.get(k)
            merged[k] = list(uval) if isinstance(uval, list) else ([] if uval is None else [str(uval)])
        elif isinstance(cur, list) and len(cur) == 0:
            uval = user.get(k)
            if isinstance(uval, list) and len(uval) > 0:
                merged[k] = list(uval)
    if not str(merged.get("name") or "").strip():
        fn = str(user.get("firstName") or "").strip()
        ln = str(user.get("lastName") or "").strip()
        if fn or ln:
            merged["name"] = f"{fn} {ln}".strip()
    return merged


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
    body_benefits = _first_present(
        body.get("desiredBenefits"),
        body.get("desiredBenefit"),
        body.get("benefits"),
        body.get("skinGoals") if mode == "skincare" else body.get("hairGoals"),
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


def _infer_product_benefit_signals(*, product: dict[str, Any], tile_product: dict[str, Any]) -> list[str]:
    out: list[str] = []
    out.extend(_product_list_values(product, "benefit", "benefits", "claims", "claim"))
    primary = _safe_scalar(product.get("primaryConcern"))
    if primary:
        out.append(primary)
    for row in (tile_product.get("ingredients") or []) + (tile_product.get("key_ingredients") or []):
        if not isinstance(row, dict):
            continue
        out.extend(_safe_list(row.get("functions")))
        out.extend(_safe_list(row.get("addresses")))
        inci_name = _safe_scalar(row.get("inci_name")).lower()
        if any(k in inci_name for k in ("hyaluron", "glycerin", "panthenol", "betaine", "sodium pca", "urea")):
            out.append("hydration")
        if any(k in inci_name for k in ("niacinamide", "ascorb", "vitamin c", "arbutin", "tranexamic")):
            out.append("brightening")
    return list(dict.fromkeys(x for x in out if isinstance(x, str) and x.strip()))


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


def _stored_triggered_observations(doc: dict[str, Any]) -> list[Any]:
    """Rehydrate observation objects; legacy rows may only have string ids in ``triggered_obs``."""
    raw = doc.get("triggered_observations")
    if isinstance(raw, list):
        if not raw:
            return []
        return raw if isinstance(raw[0], dict) else []
    legacy_ids = doc.get("triggered_obs")
    if isinstance(legacy_ids, list):
        return [{"id": sid} for sid in legacy_ids if isinstance(sid, str) and sid.strip()]
    return []


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
    doc = await scan_coll.find_one({"productId": product_ref, "analyticDetail": {"$exists": True, "$ne": None}, "ingredientAnalysisError": None}, sort=[("updatedAt", -1)])
    if not doc:
        return None
    analytic = doc.get("analyticDetail")
    return analytic if isinstance(analytic, dict) else None


async def get_profile(*, user: dict[str, Any]) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    user_details_coll = db[s.coll_user_details]
    scan_coll = db[s.coll_scan_analysis]
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    details_raw = await user_details_coll.find_one({"userId": user_id}) or {}
    details = _effective_user_details_for_match(details_raw, user)
    scans_used = await _count_scans_today(scan_coll, user.get("profileUrl"))
    profile = {
        "id": str(user_id),
        "name": details.get("name") or user.get("firstName"),
        "age": details.get("age"),
        "gender": details.get("gender"),
        "category_profiles": {
            "skin": {"type": details.get("skinType"), "concerns": _safe_list(details.get("skinConcerns")), "benefits_wanted": _safe_list(details.get("skinGoals"))},
            "hair": {"type": details.get("hairType"), "concerns": _safe_list(details.get("hairConcerns")), "benefits_wanted": _safe_list(details.get("hairGoals"))},
        },
        "safety": {
            "life_stages": _safe_list(details.get("lifeStages") or details.get("life_stages")),
            "allergies": _safe_list(details.get("allergies")),
            "conditions": _safe_list(details.get("conditions")),
            "medications": _safe_list(details.get("medications")),
        },
        "credits": {"free_used": scans_used, "free_limit": totalScanIngedientPerDay, "paid_remaining": 0},
    }
    profile["categoryProfiles"] = profile["category_profiles"]
    profile["benefitsWanted"] = {"skin": profile["category_profiles"]["skin"]["benefits_wanted"], "hair": profile["category_profiles"]["hair"]["benefits_wanted"]}
    return profile


async def patch_profile(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    db = get_scanner_db()
    user_details_coll = db[s.coll_user_details]
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    updates: dict[str, Any] = {"updatedAt": datetime.now()}
    if "name" in body:
        updates["name"] = body.get("name")
    if "age" in body:
        updates["age"] = body.get("age")
    if "gender" in body:
        updates["gender"] = body.get("gender")
    category_profiles = body.get("category_profiles") or body.get("categoryProfiles")
    if isinstance(category_profiles, dict):
        skin = category_profiles.get("skin")
        if isinstance(skin, dict):
            if "type" in skin:
                updates["skinType"] = skin.get("type")
            if "concerns" in skin:
                updates["skinConcerns"] = _as_string_list(skin.get("concerns"))
            elif "skinConcerns" in skin:
                updates["skinConcerns"] = _as_string_list(skin.get("skinConcerns"))
            if "benefits_wanted" in skin:
                updates["skinGoals"] = _as_string_list(skin.get("benefits_wanted"))
            elif "benefitsWanted" in skin:
                updates["skinGoals"] = _as_string_list(skin.get("benefitsWanted"))
            elif "skinGoals" in skin:
                updates["skinGoals"] = _as_string_list(skin.get("skinGoals"))
        hair = category_profiles.get("hair")
        if isinstance(hair, dict):
            if "type" in hair:
                updates["hairType"] = hair.get("type")
            if "concerns" in hair:
                updates["hairConcerns"] = _as_string_list(hair.get("concerns"))
            elif "hairConcerns" in hair:
                updates["hairConcerns"] = _as_string_list(hair.get("hairConcerns"))
            if "benefits_wanted" in hair:
                updates["hairGoals"] = _as_string_list(hair.get("benefits_wanted"))
            elif "benefitsWanted" in hair:
                updates["hairGoals"] = _as_string_list(hair.get("benefitsWanted"))
            elif "hairGoals" in hair:
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
    await user_details_coll.update_one({"userId": user_id}, {"$set": {"userId": user_id, **updates}}, upsert=True)
    return await get_profile(user=user)


async def score_product(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    requested_scan_id = body.get("scan_id") or body.get("scanId")
    if isinstance(requested_scan_id, str) and requested_scan_id.strip():
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
    scans_used_before = await _count_scans_today(scan_coll, user.get("profileUrl"))
    if scans_used_before >= totalScanIngedientPerDay:
        raise ScannerApiError(402, "insufficient_credits")
    user_id = _extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    details_raw = await user_details_coll.find_one({"userId": user_id}) or {}
    details = _effective_user_details_for_match(details_raw, user)
    product_ref = _normalize_product_ref(product_id)
    product = await products_coll.find_one({"_id": product_ref})
    if not product:
        raise ScannerApiError(404, "Product not found")
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
    benefits = benefits_from_body or _extract_desired_benefits(body=body, details=details, mode=mode)
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
        missing_inputs.append({"source": "profile", "fields": missing_profile_fields, "rule": "Needs validation confirmation: accept if 2 same, else 3rd value final."})
    if not benefits_from_body:
        missing_inputs.append({"source": "request", "fields": ["desiredBenefits"], "rule": "Required on every match request; do not persist to profile defaults."})
    if missing_inputs:
        raise ScannerApiError(400, f"Missing required match input(s) for {mode}", errors=missing_inputs)

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
            product_benefits=_infer_product_benefit_signals(product=product, tile_product=tile_product),
            runtime_context=runtime_context,
            base_formula=base_formula,
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
        "createdAt": now,
        "updatedAt": now,
    }
    ins = await scan_coll.insert_one(doc)
    scans_used = await _count_scans_today(scan_coll, user.get("profileUrl"))
    cta = _build_cta(state=state or "low", product_price=product.get("price"))
    legacy_analytic_detail = await _find_latest_product_analysis_detail(scan_coll=scan_coll, product_ref=product_ref)
    band_label_map = {"great": "Great Match", "good": "Good Match", "low": "Low Match", "gate": "Gate"}
    match_result: dict[str, Any] = {
        "scan_id": str(ins.inserted_id),
        "state": state,
        "band": scoring.get("band"),
        "band_label": band_label_map.get(str(scoring.get("band")), "Match"),
        "score": scoring.get("score"),
        "ceiling_applied": scoring.get("ceiling_applied"),
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
        "full_analysis": {"ingredients": tile_product.get("ingredients", []), "key_ingredients": tile_product.get("key_ingredients", []), "claims_checked": tile_product.get("claims", []), "legacy_analytic_detail": legacy_analytic_detail},
        "credits_remaining": {"free": max(0, totalScanIngedientPerDay - scans_used), "paid": 0},
        "position_reference": "Ingredient positions refer to INCI order in the formula list (lower number = higher concentration zone).",
    }
    response: dict[str, Any] = {"result": match_result}
    response.update(match_result)
    response["scanId"] = response["scan_id"]
    response["bandLabel"] = response["band_label"]
    response["ceilingApplied"] = response["ceiling_applied"]
    response["scoredFor"] = response["scored_for"]
    response["desiredBenefits"] = response["desired_benefits"]
    response["unmetNeeds"] = response["unmet_needs"]
    response["unmetProfileConcerns"] = response["unmet_profile_concerns"]
    response["unmatchedDesiredBenefits"] = response["unmatched_desired_benefits"]
    response["matchedDesiredBenefits"] = response["matched_desired_benefits"]
    response["positionReference"] = response["position_reference"]
    response["triggeredObservations"] = response["triggered_observations"]
    response["fullAnalysis"] = response["full_analysis"]
    response["creditsRemaining"] = response["credits_remaining"]
    response["baseFormula"] = response["base_formula"]
    response["overridesApplied"] = response["overrides_applied"]
    if state == "gate":
        gate_severity = "block" if safety["severity"] == "block" else "hard"
        response["gate_severity"] = gate_severity
        response["override_allowed"] = gate_severity == "hard"
        response["gate"] = {
            "title": "Not Recommended" if gate_severity == "block" else "Proceed with caution",
            "summary": (safety["triggers"][0]["explanation"] if safety["triggers"] else "Safety concern detected."),
            "evidence": (safety["triggers"][0]["explanation"] if safety["triggers"] else "Rule-based safety gate triggered."),
            "label_vs_formula": "This safety call is based on profile-to-ingredient checks, not just marketing claims.",
        }
    return response


async def submit_feedback(*, user: dict[str, Any], scan_id: str, body: dict[str, Any]) -> dict[str, Any]:
    _ = user
    if not ObjectId.is_valid(scan_id):
        raise ScannerApiError(400, "Invalid scan_id")
    sentiment = body.get("sentiment")
    if sentiment not in ("up", "down"):
        raise ScannerApiError(400, "sentiment must be 'up' or 'down'")
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    db = get_scanner_db()
    scan_coll = db[s.coll_scan_analysis]
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
    band_label_map = {"great": "Great Match", "good": "Good Match", "low": "Low Match", "gate": "Gate"}
    match_result: dict[str, Any] = {
        "scan_id": scan_id,
        "state": doc.get("state"),
        "band": doc.get("band"),
        "band_label": band_label_map.get(str(doc.get("band")), "Match"),
        "score": doc.get("score"),
        "ceiling_applied": suitability.get("ceiling_applied"),
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
    response: dict[str, Any] = {"result": match_result}
    response.update(match_result)
    response["scanId"] = response["scan_id"]
    response["bandLabel"] = response["band_label"]
    response["ceilingApplied"] = response["ceiling_applied"]
    response["unmetNeeds"] = response["unmet_needs"]
    response["scoredFor"] = response["scored_for"]
    response["desiredBenefits"] = response["desired_benefits"]
    response["profileContext"] = response["profile_context"]
    response["unmetProfileConcerns"] = response["unmet_profile_concerns"]
    response["unmatchedDesiredBenefits"] = response["unmatched_desired_benefits"]
    response["matchedDesiredBenefits"] = response["matched_desired_benefits"]
    response["positionReference"] = response["position_reference"]
    response["triggeredObservations"] = response["triggered_observations"]
    response["postScanAction"] = response["post_scan_action"]
    response["creditsRemaining"] = response["credits_remaining"]
    response["baseFormula"] = response["base_formula"]
    response["overridesApplied"] = response["overrides_applied"]
    return response

