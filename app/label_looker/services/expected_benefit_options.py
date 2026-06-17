from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection

from app.label_looker.core.errors import ScannerApiError
from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.modules.product_analysis.analysis_service_impl import (
    _best_product_type,
    _fetch_product_by_id,
    _normalize_product_ref,
    _product_list_values,
    _resolve_analysis_mode,
)

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


def _resolve_product_type_key(product: dict[str, Any]) -> str:
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


def _claim_tokens(product: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for value in _product_list_values(product, "benefit", "benefits", "claims", "claim"):
        tokens.add(_norm_token(value))
        for part in re.split(r"[,/&]+", str(value)):
            t = _norm_token(part)
            if t:
                tokens.add(t)
    primary = product.get("primaryConcern")
    if isinstance(primary, str) and primary.strip():
        tokens.add(_norm_token(primary))
    return {t for t in tokens if t}


def _entry_matches_claim(entry: dict[str, Any], claim_tokens: set[str]) -> bool:
    if not claim_tokens:
        return False
    keys = {_norm_token(entry.get("id")), _norm_token(entry.get("label"))}
    keys.update(_norm_token(x) for x in entry.get("search_terms") or [])
    return bool(keys & claim_tokens)


def _entry_matches_product_type(entry: dict[str, Any], type_row: dict[str, Any] | None) -> bool:
    if not type_row:
        return True
    related = {_norm_token(x) for x in (type_row.get("sub_types") or [])}
    related.update(_norm_token(x) for x in (type_row.get("related_types") or []))
    entry_id = _norm_token(entry.get("id"))
    entry_label = _norm_token(entry.get("label"))
    if entry_id in related or entry_label in related:
        return True
    # Sunscreen → sun protection benefits, etc.
    type_category = _norm_token(type_row.get("category"))
    entry_category = _norm_token(entry.get("category"))
    if type_category and entry_category and type_category == entry_category:
        return True
    return False


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


def build_expected_benefit_options(*, product: dict[str, Any], mode: str | None = None) -> dict[str, Any]:
    resolved_mode = _resolve_benefit_mode(product=product, mode=mode)
    type_key = _resolve_product_type_key(product)
    type_row = _product_type_row(resolved_mode, type_key)
    claim_tokens = _claim_tokens(product)
    catalog = _catalog_entries(resolved_mode)

    recommended: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _option(entry: dict[str, Any], *, recommended_flag: bool, source: str) -> dict[str, Any]:
        return {
            "id": entry["id"],
            "label": entry["label"],
            "icon": entry.get("icon"),
            "recommended": recommended_flag,
            "source": source,
        }

    for entry in catalog:
        if not _entry_matches_product_type(entry, type_row):
            continue
        if _entry_matches_claim(entry, claim_tokens):
            key = entry["id"]
            if key not in seen:
                seen.add(key)
                recommended.append(_option(entry, recommended_flag=True, source="product_claim"))

    if not recommended:
        for entry in catalog:
            if not _entry_matches_product_type(entry, type_row):
                continue
            if entry.get("is_parent"):
                key = entry["id"]
                if key not in seen:
                    seen.add(key)
                    recommended.append(_option(entry, recommended_flag=True, source="product_type"))

    for entry in catalog:
        if not _entry_matches_product_type(entry, type_row):
            continue
        key = entry["id"]
        if key in seen:
            continue
        seen.add(key)
        others.append(_option(entry, recommended_flag=False, source="catalog"))

    options = recommended + others
    if not options and catalog:
        options = [_option(e, recommended_flag=False, source="catalog_fallback") for e in catalog[:12]]

    return {
        "mode": resolved_mode,
        "productType": type_key or None,
        "productTypeLabel": (type_row or {}).get("label"),
        "expectedBenefitOptions": options[:20],
        "selectionRules": {"min": 1, "max": 3, "requiredEachScan": True},
    }


async def get_expected_benefit_options_for_product_id(
    *,
    products_coll: AsyncIOMotorCollection,
    product_id: Any,
) -> dict[str, Any]:
    product_ref = _normalize_product_ref(product_id)
    if product_ref is None:
        raise ScannerApiError(400, "productId is required")
    product = await _fetch_product_by_id(products_coll=products_coll, product_id=product_ref)
    if not product:
        raise ScannerApiError(404, "Product not found")
    out = build_expected_benefit_options(product=product)
    out["productId"] = str(product_ref)
    return out


async def get_expected_benefit_options(*, product_id: Any) -> dict[str, Any]:
    s = get_label_looker_settings()
    from app.label_looker.core.db import get_scanner_db

    db = get_scanner_db()
    return await get_expected_benefit_options_for_product_id(
        products_coll=db[s.coll_products],
        product_id=product_id,
    )


def validate_desired_benefits(
    *,
    desired: list[str],
    options_payload: dict[str, Any],
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
    cleaned: list[str] = []
    for raw in desired:
        token = _norm_token(str(raw))
        if not token:
            continue
        resolved = allowed.get(token)
        if not resolved:
            raise ScannerApiError(
                400,
                "desiredBenefits must be selected from expectedBenefitOptions for this product",
            )
        cleaned.append(resolved)
    return list(dict.fromkeys(cleaned))
