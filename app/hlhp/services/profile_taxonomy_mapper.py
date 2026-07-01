"""Map SkinBB Mongo taxonomy (skin/hair types & concerns) to HLHP profile enums.

Loads active rows from skin_concerns, skin_types, hair_concerns, hair_types
(and product_* mirrors) so every DB option resolves — not only a hardcoded subset.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Iterable

from app.hlhp.db import get_hlhp_db
from app.hlhp.models.profile import HairConcern, HairType, SkinConcern, SkinType

logger = logging.getLogger(__name__)

_TAXONOMY_COLLECTIONS = (
    "skin_concerns",
    "product_skin_concerns",
    "skin_types",
    "product_skin_types",
    "hair_concerns",
    "product_hair_concerns",
    "hair_types",
    "product_hair_types",
)

_CACHE_TTL_SEC = 300
_cache_at: float = 0.0
_skin_concern_aliases: dict[str, SkinConcern] = {}
_skin_type_aliases: dict[str, SkinType] = {}
_hair_concern_aliases: dict[str, HairConcern] = {}
_hair_type_aliases: dict[str, HairType] = {}


def normalize_taxonomy_key(value: str) -> str:
    return re.sub(r"[\s_]+", "-", (value or "").strip().lower())


def _alias_keys(*tokens: str) -> Iterable[str]:
    seen: set[str] = set()
    for token in tokens:
        if not token or not str(token).strip():
            continue
        raw = str(token).strip()
        for key in (
            normalize_taxonomy_key(raw),
            normalize_taxonomy_key(raw).replace("-", "_"),
            raw.strip().lower(),
        ):
            if key and key not in seen:
                seen.add(key)
                yield key


# Static DB value slugs (skin_bb) → HLHP enums (extends prune_taxonomy_allowlist.py).
_SKIN_CONCERN_BY_DB_SLUG: dict[str, SkinConcern] = {
    "acne": SkinConcern.ACNE,
    "breakouts": SkinConcern.ACNE,
    "blemishes": SkinConcern.ACNE,
    "pimples": SkinConcern.ACNE,
    "dryness": SkinConcern.DEHYDRATION,
    "dehydration": SkinConcern.DEHYDRATION,
    "dullness": SkinConcern.DULLNESS,
    "roughness": SkinConcern.TEXTURE,
    "oily-skin": SkinConcern.PORES,
    "oiliness": SkinConcern.PORES,
    "oily": SkinConcern.PORES,
    "enlarged-pores": SkinConcern.PORES,
    "open-pores": SkinConcern.PORES,
    "pores": SkinConcern.PORES,
    "tan": SkinConcern.TAN,
    "tanning": SkinConcern.TAN,
    "sun-damage": SkinConcern.AGING,
    "spots": SkinConcern.PIGMENTATION,
    "dark-spots": SkinConcern.PIGMENTATION,
    "hyperpigmentation": SkinConcern.PIGMENTATION,
    "pigmentation": SkinConcern.PIGMENTATION,
    "pih": SkinConcern.PIGMENTATION,
    "uneven-skintone": SkinConcern.PIGMENTATION,
    "uneven-skin-tone": SkinConcern.PIGMENTATION,
    "melasma": SkinConcern.MELASMA,
    "scars": SkinConcern.PIGMENTATION,
    "scarring": SkinConcern.PIGMENTATION,
    "dark-circles": SkinConcern.DARK_CIRCLES,
    "puffy-eyes": SkinConcern.DARK_CIRCLES,
    "under-eye": SkinConcern.DARK_CIRCLES,
    "sleep-deprivation": SkinConcern.DARK_CIRCLES,
    "rosacea": SkinConcern.REDNESS,
    "redness": SkinConcern.REDNESS,
    "fine-lines": SkinConcern.AGING,
    "wrinkles": SkinConcern.AGING,
    "sagging": SkinConcern.AGING,
    "sagging-skin": SkinConcern.AGING,
    "aging": SkinConcern.AGING,
    "anti-aging": SkinConcern.AGING,
    "sensitivity": SkinConcern.SENSITIVITY,
    "sensitive": SkinConcern.SENSITIVITY,
    "eczema": SkinConcern.SENSITIVITY,
    "texture": SkinConcern.TEXTURE,
    "heat-rash": SkinConcern.HEAT_RASH,
    "prickly-heat": SkinConcern.HEAT_RASH,
    "fungal-infection": SkinConcern.FUNGAL,
    "fungal-acne": SkinConcern.FUNGAL,
}

_HAIR_CONCERN_BY_DB_SLUG: dict[str, HairConcern] = {
    "frizz": HairConcern.FRIZZ,
    "dandruff": HairConcern.DANDRUFF,
    "hair-fall": HairConcern.THINNING,
    "hair-loss": HairConcern.THINNING,
    "hair-thinning": HairConcern.THINNING,
    "thinning": HairConcern.THINNING,
    "thinning-hair": HairConcern.THINNING,
    "brittle-hair": HairConcern.BREAKAGE,
    "split-ends": HairConcern.BREAKAGE,
    "heat-damage": HairConcern.BREAKAGE,
    "breakage": HairConcern.BREAKAGE,
    "hair-breakage": HairConcern.BREAKAGE,
    "dull-hair": HairConcern.DRYNESS,
    "oiliness": HairConcern.OILINESS,
    "oily-scalp": HairConcern.OILINESS,
    "dryness": HairConcern.DRYNESS,
    "dry-scalp": HairConcern.DRYNESS,
    "color-treated": HairConcern.COLOR_TREATED,
    "colour-treated": HairConcern.COLOR_TREATED,
    "scalp-sensitivity": HairConcern.SCALP_SENSITIVITY,
    "itchy-scalp": HairConcern.SCALP_SENSITIVITY,
}

_SKIN_TYPE_BY_DB_SLUG: dict[str, SkinType] = {
    "normal": SkinType.NORMAL,
    "normal-skin": SkinType.NORMAL,
    "dry": SkinType.DRY,
    "dry-skin": SkinType.DRY,
    "oily": SkinType.OILY,
    "oily-skin": SkinType.OILY,
    "combination": SkinType.COMBINATION,
    "sensitive": SkinType.SENSITIVE,
}

_HAIR_TYPE_BY_DB_SLUG: dict[str, HairType] = {
    "straight": HairType.STRAIGHT,
    "straight-fine": HairType.STRAIGHT,
    "straight-medium": HairType.STRAIGHT,
    "straight-thick": HairType.STRAIGHT,
    "wavy": HairType.WAVY,
    "wavy-fine": HairType.WAVY,
    "wavy-medium": HairType.WAVY,
    "curly": HairType.CURLY,
    "curly-fine": HairType.CURLY,
    "curly-medium": HairType.CURLY,
    "curly-coarse": HairType.CURLY,
    "coily": HairType.COILY,
    "kinky": HairType.COILY,
    "thinning": HairType.THINNING,
}


def _infer_skin_concern(key: str) -> SkinConcern | None:
    if key in _SKIN_CONCERN_BY_DB_SLUG:
        return _SKIN_CONCERN_BY_DB_SLUG[key]
    try:
        return SkinConcern(key.replace("-", "_"))
    except ValueError:
        pass
    # Token heuristics for labels / long slugs from Mongo.
    if any(t in key for t in ("acne", "breakout", "pimple", "blemish")):
        return SkinConcern.ACNE
    if any(t in key for t in ("melasma",)):
        return SkinConcern.MELASMA
    if any(t in key for t in ("pigment", "spot", "uneven", "scar", "pih")):
        return SkinConcern.PIGMENTATION
    if any(t in key for t in ("dark-circle", "under-eye", "puffy", "sleep")):
        return SkinConcern.DARK_CIRCLES
    if any(t in key for t in ("wrinkle", "fine-line", "sag", "aging", "sun-damage")):
        return SkinConcern.AGING
    if any(t in key for t in ("oily", "oiliness", "pore")):
        return SkinConcern.PORES
    if any(t in key for t in ("dry", "dehydr")):
        return SkinConcern.DEHYDRATION
    if any(t in key for t in ("dull",)):
        return SkinConcern.DULLNESS
    if any(t in key for t in ("red", "rosacea")):
        return SkinConcern.REDNESS
    if any(t in key for t in ("sensitive", "eczema")):
        return SkinConcern.SENSITIVITY
    if any(t in key for t in ("texture", "rough")):
        return SkinConcern.TEXTURE
    if any(t in key for t in ("fungal", "malassezia")):
        return SkinConcern.FUNGAL
    if any(t in key for t in ("heat-rash", "prickly", "heat_rash")):
        return SkinConcern.HEAT_RASH
    if "tan" in key:
        return SkinConcern.TAN
    return None


def _infer_hair_concern(key: str) -> HairConcern | None:
    if key in _HAIR_CONCERN_BY_DB_SLUG:
        return _HAIR_CONCERN_BY_DB_SLUG[key]
    try:
        return HairConcern(key.replace("-", "_"))
    except ValueError:
        pass
    if any(t in key for t in ("split", "brittle", "break", "heat-damage")):
        return HairConcern.BREAKAGE
    if any(t in key for t in ("thin", "fall", "loss")):
        return HairConcern.THINNING
    if "frizz" in key:
        return HairConcern.FRIZZ
    if "dandruff" in key:
        return HairConcern.DANDRUFF
    if any(t in key for t in ("dry", "dull")):
        return HairConcern.DRYNESS
    if any(t in key for t in ("oily", "oil")):
        return HairConcern.OILINESS
    if any(t in key for t in ("color", "colour", "dye")):
        return HairConcern.COLOR_TREATED
    if any(t in key for t in ("scalp", "itch")):
        return HairConcern.SCALP_SENSITIVITY
    return None


def _infer_skin_type(key: str) -> SkinType | None:
    if key in _SKIN_TYPE_BY_DB_SLUG:
        return _SKIN_TYPE_BY_DB_SLUG[key]
    try:
        return SkinType(key.replace("-skin", "").replace("-", "_"))
    except ValueError:
        pass
    if "combination" in key:
        return SkinType.COMBINATION
    if "sensitive" in key:
        return SkinType.SENSITIVE
    if "oily" in key:
        return SkinType.OILY
    if "dry" in key:
        return SkinType.DRY
    if "normal" in key:
        return SkinType.NORMAL
    return None


def _infer_hair_type(key: str) -> HairType | None:
    if key in _HAIR_TYPE_BY_DB_SLUG:
        return _HAIR_TYPE_BY_DB_SLUG[key]
    try:
        return HairType(key.split("-")[0])
    except ValueError:
        pass
    if key.startswith("straight"):
        return HairType.STRAIGHT
    if key.startswith("wavy"):
        return HairType.WAVY
    if key.startswith("curl") or key.startswith("coil") or key == "kinky":
        return HairType.COILY
    if "thin" in key:
        return HairType.THINNING
    return None


def _register_alias(table: dict, key: str, value: Any) -> None:
    norm = normalize_taxonomy_key(key)
    if norm and norm not in table:
        table[norm] = value


def _build_static_aliases() -> None:
    global _skin_concern_aliases, _skin_type_aliases, _hair_concern_aliases, _hair_type_aliases
    skin_c: dict[str, SkinConcern] = {}
    skin_t: dict[str, SkinType] = {}
    hair_c: dict[str, HairConcern] = {}
    hair_t: dict[str, HairType] = {}

    for slug, concern in _SKIN_CONCERN_BY_DB_SLUG.items():
        for k in _alias_keys(slug):
            _register_alias(skin_c, k, concern)

    for slug, htype in _SKIN_TYPE_BY_DB_SLUG.items():
        for k in _alias_keys(slug):
            _register_alias(skin_t, k, htype)

    for slug, concern in _HAIR_CONCERN_BY_DB_SLUG.items():
        for k in _alias_keys(slug):
            _register_alias(hair_c, k, concern)

    for slug, htype in _HAIR_TYPE_BY_DB_SLUG.items():
        for k in _alias_keys(slug):
            _register_alias(hair_t, k, htype)

    _skin_concern_aliases = skin_c
    _skin_type_aliases = skin_t
    _hair_concern_aliases = hair_c
    _hair_type_aliases = hair_t


_build_static_aliases()


async def refresh_taxonomy_aliases_from_db(*, force: bool = False) -> None:
    """Merge active Mongo taxonomy rows into the alias tables (cached)."""
    global _cache_at, _skin_concern_aliases, _skin_type_aliases, _hair_concern_aliases, _hair_type_aliases
    now = time.monotonic()
    if not force and (now - _cache_at) < _CACHE_TTL_SEC:
        return

    try:
        db = get_hlhp_db()
    except Exception as exc:
        logger.warning("HLHP taxonomy cache: DB unavailable (%s)", exc)
        return

    skin_c = dict(_skin_concern_aliases)
    skin_t = dict(_skin_type_aliases)
    hair_c = dict(_hair_concern_aliases)
    hair_t = dict(_hair_type_aliases)

    concern_colls = ("skin_concerns", "product_skin_concerns")
    type_colls = ("skin_types", "product_skin_types")
    hair_concern_colls = ("hair_concerns", "product_hair_concerns")
    hair_type_colls = ("hair_types", "product_hair_types")

    try:
        for coll_name in concern_colls:
            async for doc in db[coll_name].find({"isActive": {"$ne": False}}):
                value = str(doc.get("value") or "")
                label = str(doc.get("label") or "")
                mapped = _infer_skin_concern(normalize_taxonomy_key(value)) or _infer_skin_concern(
                    normalize_taxonomy_key(label)
                )
                if not mapped:
                    continue
                for k in _alias_keys(value, label):
                    _register_alias(skin_c, k, mapped)

        for coll_name in type_colls:
            async for doc in db[coll_name].find({"isActive": {"$ne": False}}):
                value = str(doc.get("value") or "")
                label = str(doc.get("label") or "")
                mapped = _infer_skin_type(normalize_taxonomy_key(value)) or _infer_skin_type(
                    normalize_taxonomy_key(label)
                )
                if not mapped:
                    continue
                for k in _alias_keys(value, label):
                    _register_alias(skin_t, k, mapped)

        for coll_name in hair_concern_colls:
            async for doc in db[coll_name].find({"isActive": {"$ne": False}}):
                value = str(doc.get("value") or "")
                label = str(doc.get("label") or "")
                mapped = _infer_hair_concern(normalize_taxonomy_key(value)) or _infer_hair_concern(
                    normalize_taxonomy_key(label)
                )
                if not mapped:
                    continue
                for k in _alias_keys(value, label):
                    _register_alias(hair_c, k, mapped)

        for coll_name in hair_type_colls:
            async for doc in db[coll_name].find({"isActive": {"$ne": False}}):
                value = str(doc.get("value") or "")
                label = str(doc.get("label") or "")
                mapped = _infer_hair_type(normalize_taxonomy_key(value)) or _infer_hair_type(
                    normalize_taxonomy_key(label)
                )
                if not mapped:
                    continue
                for k in _alias_keys(value, label):
                    _register_alias(hair_t, k, mapped)

        _skin_concern_aliases = skin_c
        _skin_type_aliases = skin_t
        _hair_concern_aliases = hair_c
        _hair_type_aliases = hair_t
        _cache_at = now
    except Exception as exc:
        logger.warning("HLHP taxonomy cache refresh failed: %s", exc)


def map_skin_concerns(raw_values: list[str]) -> list[SkinConcern]:
    out: list[SkinConcern] = []
    for item in raw_values:
        key = normalize_taxonomy_key(item)
        mapped = _skin_concern_aliases.get(key) or _infer_skin_concern(key)
        if mapped and mapped not in out:
            out.append(mapped)
    return out[:3]


def map_skin_type(raw_value: str | None) -> SkinType | None:
    if not raw_value or not str(raw_value).strip():
        return None
    key = normalize_taxonomy_key(str(raw_value))
    return _skin_type_aliases.get(key) or _infer_skin_type(key)


def map_hair_concerns(raw_values: list[str]) -> list[HairConcern]:
    out: list[HairConcern] = []
    for item in raw_values:
        key = normalize_taxonomy_key(item)
        mapped = _hair_concern_aliases.get(key) or _infer_hair_concern(key)
        if mapped and mapped not in out:
            out.append(mapped)
    return out[:3]


def map_hair_type(raw_value: str | None) -> HairType | None:
    if not raw_value or not str(raw_value).strip():
        return None
    key = normalize_taxonomy_key(str(raw_value))
    return _hair_type_aliases.get(key) or _infer_hair_type(key)


def supported_skin_concern_examples(limit: int = 8) -> list[str]:
    examples = sorted({c.value.replace("_", " ") for c in SkinConcern})[:limit]
    return examples
