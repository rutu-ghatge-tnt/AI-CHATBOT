from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.modules.match_my_profile.service_impl import (
    _score_product_impl,
    get_scan_result,
)
from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _fetch_product_by_id,
    ingredient_analysis_from_text,
)
from app.label_looker.services.common_flow import end_user_owns_scan_document, extract_user_id
from app.label_looker.services.label_looker_quota import (
    assert_daily_quota_available,
    get_daily_quota_snapshot,
    record_daily_quota_use,
)
from app.label_looker.services.label_looker_scan_store import (
    find_user_product_scan,
    normalize_product_id,
    scan_ids_from_doc,
)


def _enrich_match_response(
    payload: dict[str, Any],
    *,
    user_scan_id: str,
    analysis_scan_id: str,
    is_rescan: bool,
) -> dict[str, Any]:
    out = dict(payload)
    out["userScanId"] = user_scan_id
    out["scanId"] = analysis_scan_id
    if isinstance(out.get("result"), dict):
        out["result"] = dict(out["result"])
        out["result"]["user_scan_id"] = user_scan_id
        out["result"]["userScanId"] = user_scan_id
        out["result"]["scan_id"] = user_scan_id
        out["result"]["analysis_scan_id"] = analysis_scan_id
        out["result"]["analysisScanId"] = analysis_scan_id
    out["isRescan"] = is_rescan
    return out


async def get_product_scan_lookup(*, user: dict[str, Any], product_id: str) -> dict[str, Any]:
    user_id = extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")
    product_ref = normalize_product_id(product_id)
    if product_ref is None:
        raise ScannerApiError(400, "productId is required")

    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    scan_coll = db[s.coll_scan_analysis]
    doc = await find_user_product_scan(
        scan_coll=scan_coll,
        user=user,
        user_id=user_id,
        product_ref=product_ref,
        require_match=True,
    )
    if not doc:
        return {
            "hasMatch": False,
            "userScanId": None,
            "scanId": None,
            "productId": str(product_ref),
            "updatedAt": None,
        }
    user_scan_id, analysis_scan_id = scan_ids_from_doc(doc)
    updated = doc.get("updatedAt")
    return {
        "hasMatch": True,
        "userScanId": user_scan_id,
        "scanId": analysis_scan_id,
        "productId": str(product_ref),
        "updatedAt": updated.isoformat() if isinstance(updated, datetime) else updated,
        "band": doc.get("band"),
        "score": doc.get("score"),
    }


async def get_match_by_user_scan_id(*, user: dict[str, Any], user_scan_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(user_scan_id):
        raise ScannerApiError(400, "Invalid userScanId")
    payload = await get_scan_result(user=user, scan_id=user_scan_id)
    user_id = extract_user_id(user)
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    doc = await db[s.coll_scan_analysis].find_one({"_id": ObjectId(user_scan_id)})
    if not doc:
        raise ScannerApiError(404, "Scan not found")
    if user_id is None or not end_user_owns_scan_document(doc, user, user_id):
        raise ScannerApiError(403, "Forbidden")
    _, analysis_scan_id = scan_ids_from_doc(doc)
    return _enrich_match_response(
        payload,
        user_scan_id=user_scan_id,
        analysis_scan_id=analysis_scan_id,
        is_rescan=False,
    )


async def get_text_analysis(*, user: dict[str, Any], scan_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(scan_id):
        raise ScannerApiError(400, "Invalid scanId")
    user_id = extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")

    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db
    from app.label_looker.services.analysis_cache_guards import sanitize_ingredient_categorization
    from app.label_looker.modules.product_analysis.analysis_service_impl import (
        _fetch_product_by_id,
        _ingredients_from_product,
    )

    db = get_scanner_db()
    doc = await db[s.coll_scan_analysis].find_one({"_id": ObjectId(scan_id)})
    if not doc:
        raise ScannerApiError(404, "Scan not found")
    if not end_user_owns_scan_document(doc, user, user_id):
        raise ScannerApiError(403, "Forbidden")
    analytic = doc.get("analyticDetail")
    if not isinstance(analytic, dict):
        raise ScannerApiError(404, "Ingredient analysis not available for this scan")

    ingredients = doc.get("ingredients") or doc.get("extractedIngredients") or []
    if not isinstance(ingredients, list):
        ingredients = []

    product = await _fetch_product_by_id(
        products_coll=db[s.coll_products],
        product_id=doc.get("productId"),
    )
    allowed = list(ingredients)
    if product:
        from_product = await _ingredients_from_product(
            product=product,
            branded_ingredients_coll=db[s.coll_branded_ingredient],
            ingredient_coll=db[s.coll_ingredient],
        )
        if from_product:
            allowed = from_product
    cleaned, changed = sanitize_ingredient_categorization(analytic, allowed)
    if changed:
        await db[s.coll_scan_analysis].update_one(
            {"_id": ObjectId(scan_id)},
            {"$set": {"analyticDetail": cleaned}},
        )

    return {
        "scanId": scan_id,
        "userScanId": scan_id,
        "productId": str(doc.get("productId")) if doc.get("productId") is not None else None,
        "analyticDetail": cleaned,
        "ingredients": allowed if allowed else ingredients,
        "cacheHit": bool(doc.get("analysisCacheHit")),
        "cacheType": doc.get("analysisCacheType"),
    }


async def post_match_my_profile(*, user: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """
    Way 1 (insert) or Way 2B (update): ensure INCI analysis + run match on one user+product row.
    Consumes daily quota once per POST.
    """
    user_id = extract_user_id(user)
    if user_id is None:
        raise ScannerApiError(401, "Unauthorized")

    product_id = body.get("product_id") or body.get("productId")
    if not product_id:
        raise ScannerApiError(400, "productId is required")

    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    user_details_coll = db[s.coll_user_details]
    scan_coll = db[s.coll_scan_analysis]
    products_coll = db[s.coll_products]

    product_ref = normalize_product_id(product_id)
    if product_ref is None:
        raise ScannerApiError(400, "Invalid productId")
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=product_ref)
    if not product:
        raise ScannerApiError(404, "Product not found")

    await assert_daily_quota_available(user_details_coll=user_details_coll, user_id=user_id)

    existing_match = await find_user_product_scan(
        scan_coll=scan_coll,
        user=user,
        user_id=user_id,
        product_ref=product_ref,
        require_match=True,
    )
    is_rescan = existing_match is not None

    analysis_body = {
        "productId": str(product_id),
        "personalizedMatching": bool(body.get("personalizedMatching")),
        "specificType": body.get("specificType"),
        "mainBenefit": body.get("mainBenefit"),
        "langauge": body.get("langauge") or body.get("language"),
        "_orchestration": True,
    }
    analysis_result = await ingredient_analysis_from_text(body=analysis_body, user=user)
    analysis_scan_id = str(analysis_result.get("scanId") or "")

    score_body = dict(body)
    score_body["productId"] = product_id
    score_body["analysisScanId"] = analysis_scan_id
    score_body["scanId"] = analysis_scan_id

    match_payload = await _score_product_impl(
        user=user,
        body=score_body,
        quota_already_checked=True,
    )

    quota = await record_daily_quota_use(user_details_coll=user_details_coll, user_id=user_id)

    user_scan_id = str(match_payload.get("scanId") or match_payload.get("result", {}).get("scan_id") or analysis_scan_id)
    doc = await scan_coll.find_one({"_id": ObjectId(user_scan_id)}) if ObjectId.is_valid(user_scan_id) else None
    if doc:
        user_scan_id, analysis_scan_id = scan_ids_from_doc(doc)
    else:
        analysis_scan_id = analysis_scan_id or user_scan_id

    out = _enrich_match_response(
        match_payload,
        user_scan_id=user_scan_id,
        analysis_scan_id=analysis_scan_id,
        is_rescan=is_rescan,
    )
    out["analyticDetail"] = analysis_result.get("analyticDetail")
    out["ingredients"] = analysis_result.get("ingredients")
    out["analysisCacheHit"] = analysis_result.get("cacheHit")
    out["analysisCacheType"] = analysis_result.get("cacheType")
    out["creditsRemaining"] = {"free": quota["remaining"], "paid": 0}
    if isinstance(out.get("result"), dict):
        out["result"]["credits_remaining"] = out["creditsRemaining"]
    return out
