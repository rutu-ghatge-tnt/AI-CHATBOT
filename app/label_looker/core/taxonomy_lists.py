"""SkinBB taxonomy lists loaded from read-only Mongo snapshot (see scripts/fetch_taxonomy_lists.py)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "skin_bb_taxonomy.json"


@lru_cache
def load_skin_bb_taxonomy() -> dict[str, Any]:
    if not _DATA_PATH.is_file():
        return {}
    with _DATA_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def product_attributes() -> list[dict[str, Any]]:
    return list(load_skin_bb_taxonomy().get("product_attributes") or [])


def product_attribute_values() -> list[dict[str, Any]]:
    return list(load_skin_bb_taxonomy().get("product_attribute_values") or [])


def product_attribute_values_by_slug(slug: str) -> list[dict[str, Any]]:
    grouped = load_skin_bb_taxonomy().get("product_attribute_values_by_attribute") or {}
    return list(grouped.get(slug) or [])


def attribute_value_map(slug: str) -> dict[str, str]:
    maps = load_skin_bb_taxonomy().get("attribute_values_by_slug") or {}
    return dict(maps.get(slug) or {})


def benefits() -> list[dict[str, Any]]:
    return list(load_skin_bb_taxonomy().get("benefits") or [])


def benefits_by_value() -> dict[str, str]:
    return dict(load_skin_bb_taxonomy().get("benefits_by_value") or {})


def product_tags() -> list[dict[str, Any]]:
    return list(load_skin_bb_taxonomy().get("product_tags") or [])


def product_tags_by_slug() -> dict[str, str]:
    return dict(load_skin_bb_taxonomy().get("product_tags_by_slug") or {})


def tags() -> list[dict[str, Any]]:
    return list(load_skin_bb_taxonomy().get("tags") or [])


def tags_by_slug() -> dict[str, str]:
    return dict(load_skin_bb_taxonomy().get("tags_by_slug") or {})
