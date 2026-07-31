"""Guards for Label Looker product analysis cache freshness and invented ingredients."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_WS_RE = re.compile(r"\s+")


def normalize_ingredient_name(name: str) -> str:
    return _WS_RE.sub(" ", str(name or "").strip().casefold())


def coerce_to_utc(value: Any) -> datetime | None:
    """Parse Mongo/ISO timestamps into timezone-aware UTC. Naive values treated as UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        # Heuristic: ms vs seconds
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def product_updated_at(product: dict[str, Any] | None) -> datetime | None:
    if not isinstance(product, dict):
        return None
    for key in ("updatedAt", "updated_at"):
        dt = coerce_to_utc(product.get(key))
        if dt is not None:
            return dt
    return None


def analysis_cache_time(doc: dict[str, Any] | None) -> datetime | None:
    """Prefer analysis updatedAt (last write); fall back to createdAt."""
    if not isinstance(doc, dict):
        return None
    return coerce_to_utc(doc.get("updatedAt")) or coerce_to_utc(doc.get("createdAt"))


def is_analysis_fresh_for_product(
    doc: dict[str, Any] | None,
    product_updated: datetime | None,
) -> bool:
    """
    Cache is fresh when the analysis was written at/after the product's last update.

    Careful defaults:
    - No product updatedAt → keep cache (cannot judge; avoid mass bust).
    - No analysis timestamp → stale (force one regenerate to stamp the cache).
    - product.updatedAt > analysis.updatedAt → stale.
    """
    if not doc:
        return False
    if product_updated is None:
        return True
    cached_at = analysis_cache_time(doc)
    if cached_at is None:
        return False
    return cached_at >= product_updated


def _allowed_name_map(allowed: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in allowed or []:
        name = str(raw or "").strip()
        key = normalize_ingredient_name(name)
        if key and key not in out:
            out[key] = name
    return out


def filter_names_to_allowed(names: list[Any] | None, allowed: list[str] | None) -> list[str]:
    allowed_map = _allowed_name_map(allowed)
    if not allowed_map:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in names or []:
        key = normalize_ingredient_name(str(raw or ""))
        if not key or key in seen:
            continue
        canonical = allowed_map.get(key)
        if canonical is None:
            continue
        seen.add(key)
        out.append(canonical)
    return out


def sanitize_ingredient_categorization(
    analytic: dict[str, Any] | None,
    allowed_ingredients: list[str] | None,
) -> tuple[dict[str, Any], bool]:
    """
    Drop categorization entries that are not in the allowed ingredient list.

    Returns (analytic, changed).
    """
    if not isinstance(analytic, dict):
        return {}, False
    out = dict(analytic)
    cat_key = "ingredientCategorization" if "ingredientCategorization" in out else None
    if cat_key is None and "ingredient_categorization" in out:
        cat_key = "ingredient_categorization"
    if cat_key is None:
        return out, False
    cat = out.get(cat_key)
    if not isinstance(cat, dict):
        return out, False

    cleaned: dict[str, list[str]] = {}
    changed = False
    for key, values in cat.items():
        if not isinstance(values, list):
            changed = True
            cleaned[str(key)] = []
            continue
        filtered = filter_names_to_allowed(values, allowed_ingredients)
        cleaned[str(key)] = filtered
        before_norm = [normalize_ingredient_name(str(v)) for v in values if str(v).strip()]
        after_norm = [normalize_ingredient_name(v) for v in filtered]
        if before_norm != after_norm:
            changed = True

    out["ingredientCategorization"] = cleaned
    if "ingredient_categorization" in out:
        out["ingredient_categorization"] = cleaned
    return out, changed
