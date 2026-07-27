"""Resolve Active ingredient dossiers from branded → INCI for Label Looker prompts."""

from __future__ import annotations

import re
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.label_looker.core.settings import get_label_looker_settings
from app.label_looker.escape_regex import escape_regex

_ACTIVE = "active"
_DESC_MAX = 1200


def _norm_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _as_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, dict):
        raw = value.get("_id") or value.get("$oid") or value.get("id")
        return _as_object_id(raw)
    if isinstance(value, str) and ObjectId.is_valid(value.strip()):
        return ObjectId(value.strip())
    return None


def _plain_text(value: Any, *, max_len: int = _DESC_MAX) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            name = (
                str(item.get("functionalName") or "").strip()
                or str(item.get("chemicalClassName") or "").strip()
                or str(item.get("name") or "").strip()
                or str(item.get("title") or "").strip()
                or str(item.get("label") or "").strip()
            )
            if name:
                out.append(name)
    return list(dict.fromkeys(out))


def _collect_candidates(
    *,
    ingredient_names: list[str],
    product: dict[str, Any] | None,
) -> list[tuple[ObjectId | None, str]]:
    """Preserve order: product ingredient rows, then keyIngredients, then name list."""
    ordered: list[tuple[ObjectId | None, str]] = []
    seen: set[str] = set()

    def _add(oid: ObjectId | None, name: str) -> None:
        n = name.strip()
        key = str(oid) if oid is not None else _norm_name(n)
        if not key or key in seen:
            return
        if oid is None and not n:
            return
        seen.add(key)
        ordered.append((oid, n))

    for field in ("ingredients", "keyIngredients", "key_ingredients"):
        rows = (product or {}).get(field)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                oid = _as_object_id(row) or _as_object_id(row.get("ingredientId") or row.get("ingredient_id"))
                name = (
                    str(row.get("inci_name") or "").strip()
                    or str(row.get("ingredient_name") or "").strip()
                    or str(row.get("name") or "").strip()
                    or str(row.get("original_inci_name") or "").strip()
                )
                _add(oid, name)
            else:
                oid = _as_object_id(row)
                if oid is not None:
                    _add(oid, "")
                elif isinstance(row, str) and row.strip():
                    _add(None, row.strip())

    for name in ingredient_names:
        if isinstance(name, str) and name.strip():
            _add(None, name.strip())

    return ordered


def _is_active_category(value: Any) -> bool:
    return str(value or "").strip().lower() == _ACTIVE


def _pick_description(doc: dict[str, Any]) -> str:
    return _plain_text(doc.get("enhanced_description")) or _plain_text(doc.get("description"))


async def _resolve_taxonomy_names(
    coll: AsyncIOMotorCollection,
    ids: list[ObjectId],
    *,
    name_fields: tuple[str, ...],
) -> list[str]:
    if not ids:
        return []
    projection = {field: 1 for field in name_fields}
    cursor = coll.find({"_id": {"$in": ids}}, projection)
    by_id: dict[ObjectId, str] = {}
    async for doc in cursor:
        name = ""
        for field in name_fields:
            raw = doc.get(field)
            if isinstance(raw, str) and raw.strip():
                name = raw.strip()
                break
        if name:
            by_id[doc["_id"]] = name
    return [by_id[i] for i in ids if i in by_id]


async def _find_branded_doc(
    branded_coll: AsyncIOMotorCollection,
    *,
    oid: ObjectId | None,
    name: str,
) -> dict[str, Any] | None:
    if oid is not None:
        doc = await branded_coll.find_one({"_id": oid})
        if doc:
            return doc
    n = name.strip()
    if not n:
        return None
    rx = f"^{escape_regex(n)}$"
    return await branded_coll.find_one(
        {
            "$or": [
                {"ingredient_name": {"$regex": rx, "$options": "i"}},
                {"original_inci_name": {"$regex": rx, "$options": "i"}},
                {"name": {"$regex": rx, "$options": "i"}},
                {"inci_name": {"$regex": rx, "$options": "i"}},
            ]
        }
    )


async def _find_inci_doc(
    inci_coll: AsyncIOMotorCollection,
    *,
    oid: ObjectId | None,
    name: str,
) -> dict[str, Any] | None:
    if oid is not None:
        doc = await inci_coll.find_one({"_id": oid})
        if doc:
            return doc
    n = name.strip()
    if not n:
        return None
    normalized = _norm_name(n)
    doc = await inci_coll.find_one({"inciName_normalized": normalized})
    if doc:
        return doc
    rx = f"^{escape_regex(n)}$"
    return await inci_coll.find_one(
        {
            "$or": [
                {"inciName": {"$regex": rx, "$options": "i"}},
                {"name": {"$regex": rx, "$options": "i"}},
            ]
        }
    )


async def _dossier_from_branded(
    doc: dict[str, Any],
    *,
    functional_coll: AsyncIOMotorCollection,
    chemical_coll: AsyncIOMotorCollection,
) -> dict[str, Any] | None:
    if not _is_active_category(doc.get("category_decided")):
        return None
    func_ids = [_as_object_id(x) for x in (doc.get("functional_category_ids") or [])]
    chem_ids = [_as_object_id(x) for x in (doc.get("chemical_class_ids") or [])]
    functionality = await _resolve_taxonomy_names(
        functional_coll,
        [i for i in func_ids if i is not None],
        name_fields=("functionalName", "name", "title", "label"),
    )
    chemical_classes = await _resolve_taxonomy_names(
        chemical_coll,
        [i for i in chem_ids if i is not None],
        name_fields=("chemicalClassName", "name", "title", "label"),
    )
    name = (
        str(doc.get("ingredient_name") or "").strip()
        or str(doc.get("original_inci_name") or "").strip()
        or str(doc.get("name") or "").strip()
    )
    if not name:
        return None
    return {
        "name": name,
        "source": "branded",
        "functionality": functionality,
        "chemicalClasses": chemical_classes,
        "description": _pick_description(doc),
    }


def _dossier_from_inci(doc: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_active_category(doc.get("category")):
        return None
    name = str(doc.get("inciName") or "").strip() or str(doc.get("name") or "").strip()
    if not name:
        return None
    chemical_classes = _string_list(
        doc.get("chemical_class")
        or doc.get("chemicalClass")
        or doc.get("chemicalClasses")
        or doc.get("chemical_classes")
    )
    return {
        "name": name,
        "source": "inci",
        "functionality": _string_list(doc.get("functionality")),
        "chemicalClasses": chemical_classes,
        "description": _plain_text(doc.get("description")),
    }


def format_active_dossiers_for_prompt(dossiers: list[dict[str, Any]]) -> str:
    if not dossiers:
        return ""
    blocks: list[str] = []
    for idx, d in enumerate(dossiers, start=1):
        functionality = ", ".join(d.get("functionality") or []) or "n/a"
        chemical = ", ".join(d.get("chemicalClasses") or []) or "n/a"
        description = str(d.get("description") or "").strip() or "n/a"
        blocks.append(
            f"{idx}. Name: {d.get('name')}\n"
            f"   Functionality: {functionality}\n"
            f"   Chemical class: {chemical}\n"
            f"   Description: {description}"
        )
    return "\n".join(blocks)


# Functional category / dossier text → match-engine benefit signals
_FUNCTIONALITY_SIGNAL_MAP: dict[str, tuple[str, ...]] = {
    "antioxidant": ("antioxidant", "brightening", "anti-aging", "Brightens and evens skin tone"),
    "skin conditioning agent": ("barrier repair", "soothing", "skin conditioning"),
    "skin conditioning": ("barrier repair", "soothing", "skin conditioning"),
    "anti-aging": ("anti-aging", "brightening"),
    "anti ageing": ("anti-aging", "brightening"),
    "brightening": ("brightening", "Brightens and evens skin tone", "uneven skin tone", "uneven-skintone"),
    "whitening": ("brightening", "Brightens and evens skin tone"),
    "lightening": ("brightening", "Brightens and evens skin tone"),
    "humectant": ("hydration", "moisturizing"),
    "moisturising": ("hydration", "moisturizing"),
    "moisturizing": ("hydration", "moisturizing"),
    "emollient": ("barrier repair", "moisturizing"),
    "soothing": ("soothing", "calming"),
    "anti-inflammatory": ("soothing", "calming"),
    "protective agent": ("antioxidant", "anti-aging"),
}

_BRIGHTENING_CORPUS_HINTS = (
    "brighten",
    "brightening",
    "radiant",
    "radiance",
    "glow",
    "even tone",
    "even-toned",
    "uneven",
    "pigment",
    "glutathione",
    "depigment",
    "lighter",
    "luminosity",
    "tone correction",
)

_HYDRATION_CORPUS_HINTS = (
    "hydrat",
    "moisture",
    "humectant",
    "moisturiz",
    "moisturis",
)


def _dossier_corpus(dossiers: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for d in dossiers:
        name = str(d.get("name") or "").strip()
        if name:
            parts.append(name)
        for fn in d.get("functionality") or []:
            if str(fn).strip():
                parts.append(str(fn).strip())
        for chem in d.get("chemicalClasses") or []:
            if str(chem).strip():
                parts.append(str(chem).strip())
        desc = str(d.get("description") or "").strip()
        if desc:
            parts.append(desc)
    return " ".join(parts).lower()


def benefit_signals_from_active_dossiers(
    dossiers: list[dict[str, Any]],
    *,
    mode: str = "skincare",
) -> list[str]:
    """
    Convert Active ingredient dossiers into product benefit signals for Match My Profile scoring.
    """
    if not dossiers:
        return []

    out: list[str] = []
    for d in dossiers:
        for fn in d.get("functionality") or []:
            label = str(fn).strip()
            if not label:
                continue
            out.append(label)
            mapped = _FUNCTIONALITY_SIGNAL_MAP.get(label.lower())
            if mapped:
                out.extend(mapped)

    corpus = _dossier_corpus(dossiers)
    if any(hint in corpus for hint in _BRIGHTENING_CORPUS_HINTS):
        out.extend(
            [
                "brightening",
                "Brightens and evens skin tone",
                "uneven skin tone",
                "uneven-skintone",
                "pigmentation",
                "anti-aging",
            ]
        )
    if any(hint in corpus for hint in _HYDRATION_CORPUS_HINTS):
        out.extend(["hydration", "moisturizing", "dryness"])

    # Taxonomy catalog labels from dossier text (same needle matching as marketing claims)
    try:
        from app.label_looker.services.product_marketing_signals import match_benefit_labels_from_marketing

        fake_product = {
            "name": "",
            "description": corpus,
            "benefit": [],
            "benefits": [],
            "claims": [],
            "claim": [],
        }
        out.extend(
            match_benefit_labels_from_marketing(
                product=fake_product,
                tag_names=[],
                mode=mode,
            )
        )
    except Exception:
        pass

    return list(dict.fromkeys(x for x in out if isinstance(x, str) and x.strip()))


async def resolve_active_ingredient_dossiers(
    *,
    ingredient_names: list[str],
    product: dict[str, Any] | None = None,
    db: AsyncIOMotorDatabase | None = None,
) -> list[dict[str, Any]]:
    """
    For each formula ingredient: look up branded first, then INCI.
    Include only Active rows (category_decided / category). Do not skip on approved/isDeleted.
    """
    s = get_label_looker_settings()
    if db is None:
        from app.label_looker.core.db import get_scanner_db

        db = get_scanner_db()

    branded_coll = db[s.coll_branded_ingredient]
    inci_coll = db[s.coll_inci]
    functional_coll = db[s.coll_functional_categories]
    chemical_coll = db[s.coll_chemical_classes]

    candidates = _collect_candidates(ingredient_names=ingredient_names, product=product)
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for oid, name in candidates:
        branded = await _find_branded_doc(branded_coll, oid=oid, name=name)
        dossier: dict[str, Any] | None = None
        if branded is not None:
            dossier = await _dossier_from_branded(
                branded,
                functional_coll=functional_coll,
                chemical_coll=chemical_coll,
            )
            # Branded hit that is not Active: do not fall through to INCI for the same ref.
            if dossier is None:
                continue
        else:
            inci_oid = oid
            inci_name = name
            # If branded was missing but we only had an ObjectId that wasn't branded, still try INCI by id/name.
            inci = await _find_inci_doc(inci_coll, oid=inci_oid, name=inci_name)
            if inci is not None:
                dossier = _dossier_from_inci(inci)

        if not dossier:
            continue
        key = _norm_name(str(dossier.get("name") or ""))
        if not key or key in seen_names:
            continue
        seen_names.add(key)
        out.append(dossier)

    return out
