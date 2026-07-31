from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.services.analysis_cache_guards import (
    is_analysis_fresh_for_product,
    sanitize_ingredient_categorization,
)


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


def product_analysis_lookup_filter(product_ref: Any) -> dict[str, Any]:
    ref = _normalize_product_ref(product_ref)
    if ref is None:
        return {"productId": None}
    if isinstance(ref, ObjectId):
        return {"$or": [{"_id": ref}, {"productId": ref}]}
    return {"productId": ref}


def is_successful_product_analysis(doc: dict[str, Any] | None) -> bool:
    if not doc:
        return False
    if doc.get("ingredientAnalysisError"):
        return False
    analytic = doc.get("analyticDetail")
    return isinstance(analytic, dict) and len(analytic) > 0


async def find_product_analysis(
    *,
    coll: AsyncIOMotorCollection,
    product_ref: Any,
    product_updated: datetime | None = None,
    delete_if_stale: bool = True,
) -> dict[str, Any] | None:
    """
    Load a successful catalog analysis.

    When product_updated is provided and the cache is older than that timestamp,
    optionally delete the stale catalog cache and return None so callers regenerate.
    """
    ref = _normalize_product_ref(product_ref)
    if ref is None:
        return None
    filt = product_analysis_lookup_filter(ref)
    doc = await coll.find_one(filt)
    if not is_successful_product_analysis(doc):
        return None
    if not is_analysis_fresh_for_product(doc, product_updated):
        if delete_if_stale:
            await coll.delete_many(filt)
        return None
    return doc


async def upsert_product_analysis(
    *,
    coll: AsyncIOMotorCollection,
    product_ref: Any,
    product: dict[str, Any] | None,
    analytic_detail: dict[str, Any],
    ingredients: list[str],
    specific_type: str | None = None,
    main_benefit: str | None = None,
    source: str = "runtime",
    model: str | None = None,
    error: str | None = None,
) -> None:
    ref = _normalize_product_ref(product_ref)
    if ref is None:
        return
    now = datetime.now(timezone.utc)
    product_name = None
    if isinstance(product, dict):
        product_name = product.get("productName") or product.get("name")
    ing_list = [str(x) for x in ingredients] if isinstance(ingredients, list) else []
    cleaned_analytic, _ = sanitize_ingredient_categorization(
        analytic_detail if isinstance(analytic_detail, dict) else {},
        ing_list,
    )
    set_doc: dict[str, Any] = {
        "productId": ref,
        "productName": product_name,
        "analyticDetail": cleaned_analytic,
        "ingredients": ing_list,
        "specificType": specific_type,
        "mainBenefit": main_benefit,
        "source": source,
        "model": model,
        "ingredientAnalysisError": error,
        "updatedAt": now,
    }
    await coll.update_one(
        product_analysis_lookup_filter(ref),
        {
            "$set": set_doc,
            "$setOnInsert": {"createdAt": now},
        },
        upsert=True,
    )


async def list_analyzed_product_ids(*, coll: AsyncIOMotorCollection) -> set[str]:
    ids: set[str] = set()
    cursor = coll.find(
        {"analyticDetail": {"$exists": True, "$ne": None}, "ingredientAnalysisError": None},
        {"productId": 1, "_id": 1},
    )
    async for doc in cursor:
        pid = doc.get("productId") or doc.get("_id")
        if pid is not None:
            ids.add(str(pid))
    return ids


def get_product_analysis_collection():
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    return db[s.coll_product_analysis]
