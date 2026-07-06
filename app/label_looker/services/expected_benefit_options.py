from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.taxonomy_lists import load_skin_bb_taxonomy
from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _best_product_type,
    _fetch_product_by_id,
    _normalize_product_ref,
    _product_list_values,
    _resolve_analysis_mode,
)
from app.label_looker.services.product_marketing_signals import resolve_product_tag_names

_LIP_BENEFIT_IDS = frozenset(
    {
        "hydration",
        "moisturizing",
        "sun_protection",
        "spf_protection",
        "pigmentation",
        "brightening",
        "exfoliation",
        "smoothing",
        "plumping",
        "barrier_repair",
        "soothing",
        "anti_aging",
    }
)

_BODY_BENEFIT_IDS = frozenset(
    {
        "hydration",
        "moisturizing",
        "exfoliation",
        "brightening",
        "smoothing",
        "firming",
        "sun_protection",
        "spf_protection",
        "soothing",
        "anti_aging",
        "tanning",
        "cellulite",
    }
)


@lru_cache
def _load_taxonomy() -> dict[str, Any]:
    candidates = [
        Path(__file__).resolve().parents[3] / "enhanced_formulynx_taxonomy.json",
        Path.cwd() / "enhanced_formulynx_taxonomy.json",
    ]
    for path in candidates:
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                return json.load(fh)
    return {}


def _norm_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _benefit_catalog_key(mode: str) -> str:
    if mode == "haircare":
        return "hair_benefits"
    return "skin_benefits"


def _allowed_benefit_ids(mode: str) -> frozenset[str] | None:
    if mode == "lipcare":
        return _LIP_BENEFIT_IDS
    if mode == "bodycare":
        return _BODY_BENEFIT_IDS
    return None


def _catalog_entries(mode: str) -> list[dict[str, Any]]:
    taxonomy = _load_taxonomy()
    raw = taxonomy.get(_benefit_catalog_key(mode)) or {}
    if not isinstance(raw, dict):
        return []
    allowed = _allowed_benefit_ids(mode)
    out: list[dict[str, Any]] = []
    for bid, row in raw.items():
        if not isinstance(row, dict):
            continue
        entry_id = str(row.get("id") or bid).strip()
        label = str(row.get("label") or entry_id).strip()
        if not label:
            continue
        if allowed is not None and entry_id not in allowed and _norm_token(label) not in allowed:
            continue
        out.append(
            {
                "id": entry_id,
                "label": label,
                "icon": row.get("icon"),
                "category": row.get("category"),
                "is_parent": bool(row.get("is_parent")),
                "search_terms": list(row.get("search_terms") or []),
            }
        )
    return out


def _resolve_product_type_key(
    product: dict[str, Any],
    *,
    tag_names: list[str] | None = None,
) -> str:
    marketing_corpus = " ".join(
        [
            str(product.get("productType") or ""),
            str(product.get("subCategory") or product.get("subcategory") or ""),
            str(product.get("productName") or product.get("name") or ""),
            " ".join(tag_names or []),
        ]
    ).lower()
    for needle, type_key in (
        ("hair cleanser", "shampoo"),
        ("shampoo", "shampoo"),
        ("conditioner", "conditioner"),
        ("hair mask", "hair_mask"),
        ("hair oil", "hair_oil"),
        ("hair serum", "hair_serum"),
    ):
        if needle in marketing_corpus:
            return type_key
    for raw in (
        product.get("productType"),
        product.get("subCategory"),
        product.get("subcategory"),
        _best_product_type(product),
        product.get("productName"),
        product.get("name"),
    ):
        token = _norm_token(str(raw or ""))
        if token:
            return token
    return ""


def _product_type_row(mode: str, type_key: str) -> dict[str, Any] | None:
    if not type_key:
        return None
    taxonomy = _load_taxonomy()
    types_key = "hair_product_types" if mode == "haircare" else "skin_product_types"
    types = taxonomy.get(types_key) or {}
    if not isinstance(types, dict):
        return None
    if type_key in types and isinstance(types[type_key], dict):
        return types[type_key]
    for tid, row in types.items():
        if not isinstance(row, dict):
            continue
        labels = [str(row.get("label") or ""), str(tid)]
        labels.extend(str(x) for x in (row.get("search_terms") or []))
        for label in labels:
            if _norm_token(label) == type_key:
                return row
        if type_key in _norm_token(str(row.get("label") or "")):
            return row
    return None


def _benefit_display_label(doc: dict[str, Any]) -> str | None:
    for key in ("name", "label", "title", "value"):
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


@lru_cache
def _taxonomy_benefit_labels_by_id() -> dict[str, str]:
    out: dict[str, str] = {}
    taxonomy = load_skin_bb_taxonomy()
    for key in ("product_attribute_values", "benefits"):
        rows = taxonomy.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id") or row.get("_id") or "").strip()
            label = _benefit_display_label(row)
            if rid and label:
                out[rid] = label
    return out


def _benefit_rows_from_product(product: dict[str, Any]) -> list[Any]:
    combined: list[Any] = []
    for key in ("benefit", "benefits"):
        raw = product.get(key)
        if isinstance(raw, list):
            combined.extend(raw)
    return combined


_BENEFIT_REF_COLLECTIONS = (
    "product_attribute_values",
    "benefits",
    "skin_benefits",
    "hair_benefits",
)


async def _resolve_benefit_object_ids(
    db: AsyncIOMotorDatabase,
    ids: list[ObjectId],
) -> dict[ObjectId, str]:
    resolved: dict[ObjectId, str] = {}
    pending = list(ids)
    for coll_name in _BENEFIT_REF_COLLECTIONS:
        if not pending:
            break
        coll = db[coll_name]
        cursor = coll.find(
            {"_id": {"$in": pending}},
            {"name": 1, "title": 1, "label": 1, "value": 1},
        )
        async for doc in cursor:
            oid = doc.get("_id")
            if not isinstance(oid, ObjectId):
                continue
            label = _benefit_display_label(doc)
            if label:
                resolved[oid] = label
        pending = [oid for oid in pending if oid not in resolved]
    snap = _taxonomy_benefit_labels_by_id()
    for oid in pending:
        label = snap.get(str(oid))
        if label:
            resolved[oid] = label
    return resolved


async def resolve_product_benefit_labels(
    *,
    db: AsyncIOMotorDatabase,
    product: dict[str, Any],
) -> list[str]:
    """Resolve product.benefit / product.benefits ObjectId refs to display labels."""
    from app.label_looker.services.profile_taxonomy_resolver import (
        _collect_object_ids,
        _resolve_list_values,
    )

    combined = _benefit_rows_from_product(product)
    if not combined:
        return _product_list_values(product, "benefit", "benefits")
    ids = _collect_object_ids(combined)
    resolved = await _resolve_benefit_object_ids(db, ids) if ids else {}
    labels = _resolve_list_values(combined, resolved)
    if labels:
        return labels
    return _product_list_values(product, "benefit", "benefits")


def _resolve_benefit_mode(*, product: dict[str, Any], mode: str | None) -> str:
    if mode in {"skincare", "haircare", "lipcare", "bodycare"}:
        return mode
    product_type = str(product.get("productType") or "").lower()
    product_name = str(product.get("productName") or product.get("name") or "").lower()
    hair_markers = ("hair", "scalp", "shampoo", "conditioner", "mask", "serum")
    if any(m in product_type or m in product_name for m in hair_markers):
        if "hair" in product_name or "scalp" in product_name or "shampoo" in product_type or "conditioner" in product_type:
            return "haircare"
    if "lip" in product_type or "lip" in product_name:
        return "lipcare"
    if "body" in product_type and "face" not in product_name:
        return "bodycare"
    return _resolve_analysis_mode(body={}, product=product, specific_type=None, main_benefit=None)


def build_expected_benefit_options(
    *,
    product: dict[str, Any],
    mode: str | None = None,
    tag_names: list[str] | None = None,
    benefit_labels: list[str] | None = None,
) -> dict[str, Any]:
    resolved_mode = _resolve_benefit_mode(product=product, mode=mode)
    type_key = _resolve_product_type_key(product, tag_names=tag_names)
    type_row = _product_type_row(resolved_mode, type_key)
    product_benefits = (
        benefit_labels
        if benefit_labels is not None
        else _product_list_values(product, "benefit", "benefits")
    )

    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    for label in product_benefits:
        key = _norm_token(label)
        if key in seen:
            continue
        seen.add(key)
        options.append(
            {
                "id": key,
                "label": label,
                "icon": None,
                "recommended": True,
                "source": "product",
            }
        )

    return {
        "mode": resolved_mode,
        "productType": type_key or None,
        "productTypeLabel": (type_row or {}).get("label"),
        "expectedBenefitOptions": options,
        "selectionRules": {"min": 1, "max": 3, "requiredEachScan": True},
        "tagNames": list(tag_names or []),
    }


async def get_expected_benefit_options_for_product_id(
    *,
    products_coll: AsyncIOMotorCollection,
    product_id: Any,
    tags_coll: AsyncIOMotorCollection | None = None,
) -> dict[str, Any]:
    product_ref = _normalize_product_ref(product_id)
    if product_ref is None:
        raise ScannerApiError(400, "productId is required")
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=product_ref)
    if not product:
        raise ScannerApiError(404, "Product not found")
    tag_names: list[str] | None = None
    if tags_coll is not None:
        tag_names = await resolve_product_tag_names(product=product, tags_coll=tags_coll)
    benefit_labels = await resolve_product_benefit_labels(db=products_coll.database, product=product)
    out = build_expected_benefit_options(
        product=product,
        tag_names=tag_names,
        benefit_labels=benefit_labels,
    )
    out["productId"] = str(product_ref)
    return out


async def get_expected_benefit_options(*, product_id: Any) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    return await get_expected_benefit_options_for_product_id(
        products_coll=db[s.coll_products],
        product_id=product_id,
        tags_coll=db["product_tags"],
    )


def _resolve_desired_benefit_label(
    raw: str,
    *,
    allowed: dict[str, str],
    mode: str,
    product: dict[str, Any] | None = None,
    tag_names: list[str] | None = None,
) -> str | None:
    del mode, product, tag_names
    token = _norm_token(raw)
    if token in allowed:
        return allowed[token]
    raw_lower = str(raw or "").strip().lower()
    for label in allowed.values():
        if label.lower() == raw_lower:
            return label
    return None


def validate_desired_benefits(
    *,
    desired: list[str],
    options_payload: dict[str, Any],
    product: dict[str, Any] | None = None,
    tag_names: list[str] | None = None,
) -> list[str]:
    """Return normalized labels; raise ScannerApiError if any selection is outside options."""
    allowed: dict[str, str] = {}
    for row in options_payload.get("expectedBenefitOptions") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()
        bid = str(row.get("id") or "").strip()
        if label:
            allowed[_norm_token(label)] = label
        if bid:
            allowed[_norm_token(bid)] = label or bid
    mode = str(options_payload.get("mode") or "skincare")
    resolved_tags = tag_names if tag_names is not None else list(options_payload.get("tagNames") or [])
    cleaned: list[str] = []
    for raw in desired:
        if not str(raw).strip():
            continue
        resolved = _resolve_desired_benefit_label(
            str(raw),
            allowed=allowed,
            mode=mode,
            product=product,
            tag_names=resolved_tags,
        )
        if not resolved:
            raise ScannerApiError(
                400,
                "desiredBenefits must be selected from expectedBenefitOptions for this product",
            )
        cleaned.append(resolved)
    return list(dict.fromkeys(cleaned))
