from __future__ import annotations

import re
from html import unescape
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection


def _norm_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return unescape(re.sub(r"\s+", " ", text)).strip()


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


def _collect_tag_ids(product: dict[str, Any]) -> list[ObjectId]:
    out: list[ObjectId] = []
    seen: set[ObjectId] = set()
    for raw in product.get("tags") or []:
        oid = _normalize_object_id(raw)
        if oid is not None and oid not in seen:
            seen.add(oid)
            out.append(oid)
    return out


async def resolve_product_tag_names(
    *,
    product: dict[str, Any],
    tags_coll: AsyncIOMotorCollection,
) -> list[str]:
    tag_ids = _collect_tag_ids(product)
    if not tag_ids:
        return []
    names: list[str] = []
    seen: set[str] = set()
    async for doc in tags_coll.find({"_id": {"$in": tag_ids}}):
        name = str(doc.get("name") or doc.get("label") or doc.get("title") or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _product_scalar_values(product: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for key in keys:
        raw = product.get(key)
        if isinstance(raw, str) and raw.strip():
            out.append(raw.strip())
    return out


def _marketing_corpus(*, product: dict[str, Any], tag_names: list[str] | None) -> str:
    parts: list[str] = []
    parts.extend(_product_scalar_values(product, "productName", "name", "title", "primaryConcern"))
    for key in ("benefit", "benefits", "claims", "claim"):
        raw = product.get(key)
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict):
                    label = str(row.get("label") or row.get("name") or "").strip()
                    if label:
                        parts.append(label)
                elif isinstance(row, str) and row.strip():
                    parts.append(row.strip())
        elif isinstance(raw, str) and raw.strip():
            parts.append(raw.strip())
    description = product.get("description") or product.get("shortDescription") or product.get("summary")
    if isinstance(description, str) and description.strip():
        parts.append(_strip_html(description))
    parts.extend(tag_names or [])
    return " ".join(parts).lower()


def _catalog_entries(mode: str) -> list[dict[str, Any]]:
    from app.label_looker.services.expected_benefit_options import _catalog_entries

    return _catalog_entries(mode)


def match_benefit_labels_from_marketing(
    *,
    product: dict[str, Any],
    tag_names: list[str] | None,
    mode: str,
) -> list[str]:
    corpus = _marketing_corpus(product=product, tag_names=tag_names)
    if not corpus.strip():
        return []
    matched: list[str] = []
    seen: set[str] = set()
    for entry in _catalog_entries(mode):
        label = str(entry.get("label") or "").strip()
        if not label:
            continue
        needles = [label, *list(entry.get("search_terms") or [])]
        for needle in needles:
            needle_text = str(needle or "").strip().lower()
            if len(needle_text) < 3:
                continue
            if needle_text in corpus:
                if label not in seen:
                    seen.add(label)
                    matched.append(label)
                break
    return matched


def marketing_claim_tokens(
    *,
    product: dict[str, Any],
    tag_names: list[str] | None,
    mode: str,
) -> set[str]:
    tokens: set[str] = set()
    for value in _marketing_corpus(product=product, tag_names=tag_names).split():
        t = _norm_token(value)
        if t:
            tokens.add(t)
    for label in match_benefit_labels_from_marketing(product=product, tag_names=tag_names, mode=mode):
        tokens.add(_norm_token(label))
    for name in tag_names or []:
        tokens.add(_norm_token(name))
        for part in re.split(r"[,/&]+", str(name)):
            t = _norm_token(part)
            if t:
                tokens.add(t)
    return {t for t in tokens if t}


def build_product_benefit_signals(
    *,
    product: dict[str, Any],
    tile_product: dict[str, Any],
    tag_names: list[str] | None = None,
    mode: str = "skincare",
    active_dossiers: list[dict[str, Any]] | None = None,
) -> list[str]:
    out: list[str] = []
    for key in ("benefit", "benefits", "claims", "claim"):
        raw = product.get(key)
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict):
                    label = str(row.get("label") or row.get("name") or "").strip()
                    if label:
                        out.append(label)
                elif isinstance(row, str) and row.strip():
                    out.append(row.strip())
        elif isinstance(raw, str) and raw.strip():
            out.append(raw.strip())
    primary = product.get("primaryConcern")
    if isinstance(primary, str) and primary.strip():
        out.append(primary.strip())
    out.extend(tag_names or [])
    out.extend(match_benefit_labels_from_marketing(product=product, tag_names=tag_names, mode=mode))
    for row in (tile_product.get("ingredients") or []) + (tile_product.get("key_ingredients") or []):
        if not isinstance(row, dict):
            continue
        for fn_key in ("functions", "addresses"):
            raw = row.get(fn_key)
            if isinstance(raw, list):
                out.extend(str(x).strip() for x in raw if str(x).strip())
        inci_name = str(row.get("inci_name") or "").lower()
        if any(k in inci_name for k in ("hyaluron", "glycerin", "panthenol", "betaine", "sodium pca", "urea")):
            out.append("hydration")
        if any(
            k in inci_name
            for k in (
                "niacinamide",
                "ascorb",
                "vitamin c",
                "arbutin",
                "tranexamic",
                "tetrahydrocurcumin",
                "curcumin",
                "glutamylcysteine",
                "glyteine",
                "tocopheryl",
                "tocopherol",
            )
        ):
            out.append("brightening")
            out.append("Brightens and evens skin tone")
            out.append("anti-aging")
        if "keratin" in inci_name:
            out.append("Repair")

    if active_dossiers:
        from app.label_looker.services.active_ingredient_dossiers import benefit_signals_from_active_dossiers

        out.extend(benefit_signals_from_active_dossiers(active_dossiers, mode=mode))

    return list(dict.fromkeys(x for x in out if isinstance(x, str) and x.strip()))
