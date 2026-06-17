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
from app.label_looker.services.product_marketing_signals import (
    marketing_claim_tokens,
    match_benefit_labels_from_marketing,
    resolve_product_tag_names,
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


def _claim_tokens(
    product: dict[str, Any],
    *,
    tag_names: list[str] | None = None,
    mode: str = "skincare",
) -> set[str]:
    tokens = marketing_claim_tokens(product=product, tag_names=tag_names, mode=mode)
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


def build_expected_benefit_options(
    *,
    product: dict[str, Any],
    mode: str | None = None,
    tag_names: list[str] | None = None,
) -> dict[str, Any]:
    resolved_mode = _resolve_benefit_mode(product=product, mode=mode)
    type_key = _resolve_product_type_key(product, tag_names=tag_names)
    type_row = _product_type_row(resolved_mode, type_key)
    claim_tokens = _claim_tokens(product, tag_names=tag_names, mode=resolved_mode)
    catalog = _catalog_entries(resolved_mode)
    max_options = 35 if resolved_mode == "haircare" else 20

    recommended: list[dict[str, Any]] = []
    parents: list[dict[str, Any]] = []
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
        if not entry.get("is_parent"):
            continue
        key = entry["id"]
        if key in seen:
            continue
        if resolved_mode != "haircare" and type_row is not None and not _entry_matches_product_type(entry, type_row):
            continue
        seen.add(key)
        parents.append(_option(entry, recommended_flag=False, source="catalog_parent"))

    for entry in catalog:
        if entry.get("is_parent"):
            continue
        if type_row is not None and not _entry_matches_product_type(entry, type_row):
            continue
        key = entry["id"]
        if key in seen:
            continue
        seen.add(key)
        others.append(_option(entry, recommended_flag=False, source="catalog"))

    options = recommended + parents + others
    if not options and catalog:
        options = [_option(e, recommended_flag=False, source="catalog_fallback") for e in catalog[:max_options]]

    return {
        "mode": resolved_mode,
        "productType": type_key or None,
        "productTypeLabel": (type_row or {}).get("label"),
        "expectedBenefitOptions": options[:max_options],
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
    out = build_expected_benefit_options(product=product, tag_names=tag_names)
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
    token = _norm_token(raw)
    if token in allowed:
        return allowed[token]

    raw_lower = str(raw or "").strip().lower()
    if product is not None:
        tag_candidates = list(tag_names or [])
        if raw_lower:
            tag_candidates.append(raw)
        for tag in tag_candidates:
            if not str(tag).strip():
                continue
            if _norm_token(tag) != token and raw_lower != str(tag).strip().lower():
                continue
            for label in match_benefit_labels_from_marketing(
                product=product,
                tag_names=[str(tag)],
                mode=mode,
            ):
                normalized = _norm_token(label)
                if normalized in allowed:
                    return allowed[normalized]
        for label in match_benefit_labels_from_marketing(
            product=product,
            tag_names=tag_candidates,
            mode=mode,
        ):
            normalized = _norm_token(label)
            if normalized in allowed and normalized in token:
                return allowed[normalized]

    for entry in _catalog_entries(mode):
        label = str(entry.get("label") or "").strip()
        if not label:
            continue
        candidates = {_norm_token(label), _norm_token(str(entry.get("id") or ""))}
        candidates.update(_norm_token(str(x)) for x in entry.get("search_terms") or [])
        if token in candidates:
            normalized = _norm_token(label)
            if normalized in allowed:
                return allowed[normalized]
        for term in entry.get("search_terms") or []:
            term_lower = str(term).strip().lower()
            if len(term_lower) >= 4 and term_lower in raw_lower:
                normalized = _norm_token(label)
                if normalized in allowed:
                    return allowed[normalized]
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
