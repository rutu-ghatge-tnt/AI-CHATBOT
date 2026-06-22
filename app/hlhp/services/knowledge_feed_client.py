"""Fetch Knowledge Feed posts from SkinBB CMS for HLHP Explore."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.hlhp.config import hl_settings

logger = logging.getLogger(__name__)

_KNOWLEDGE_CATEGORIES = ("jargons", "skinvestigators", "stories")
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _unwrap_posts(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("posts"), list):
        return [p for p in data["posts"] if isinstance(p, dict)]
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(payload.get("posts"), list):
        return [p for p in payload["posts"] if isinstance(p, dict)]
    return []


def _image_url(node: Any) -> str | None:
    if isinstance(node, dict):
        url = node.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    if isinstance(node, str) and node.strip():
        return node.strip()
    return None


def _category_slug(post: dict[str, Any], fallback: str) -> str:
    for key in ("categorySlug",):
        val = post.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    category = post.get("category")
    if isinstance(category, dict):
        slug = category.get("slug")
        if isinstance(slug, str) and slug.strip():
            return slug.strip().lower()
    categories = post.get("categories")
    if isinstance(categories, list):
        for item in categories:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip().lower()
            if slug:
                return slug
    return fallback


def _strip_html(value: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _content_type_label(category_slug: str) -> str:
    if "jargon" in category_slug:
        return "Jargon Buster"
    if "skinvestigator" in category_slug:
        return "Skinvestigator"
    return "Real Life Story"


def normalize_knowledge_post(post: dict[str, Any], *, fallback_category: str) -> dict[str, Any] | None:
    slug = str(post.get("slug") or "").strip()
    title = _strip_html(str(post.get("title") or "").strip())
    if not slug or not title:
        return None
    category_slug = _category_slug(post, fallback_category)
    raw_excerpt = str(
        post.get("shortDescription") or post.get("excerpt") or post.get("content") or ""
    ).strip()
    excerpt = _strip_html(raw_excerpt)[:280]
    tag_slugs: list[str] = []
    for tag in post.get("tags") or []:
        if isinstance(tag, dict):
            for key in ("slug", "name"):
                val = tag.get(key)
                if isinstance(val, str) and val.strip():
                    tag_slugs.append(val.strip().lower().replace(" ", "-"))
                    break
        elif isinstance(tag, str) and tag.strip():
            tag_slugs.append(tag.strip().lower().replace(" ", "-"))

    return {
        "post_id": str(post.get("_id") or slug),
        "slug": slug,
        "category_slug": category_slug,
        "content_type": _content_type_label(category_slug),
        "title": title,
        "excerpt": excerpt,
        "thumbnail_url": _image_url(post.get("featuredImage")) or _image_url(post.get("thumbnail")),
        "tag_slugs": tag_slugs,
        "read_time": post.get("readTime"),
    }


async def _fetch_category(client: httpx.AsyncClient, category: str, *, limit: int) -> list[dict[str, Any]]:
    url = f"{hl_settings.SKINBB_API_BASE_URL}/api/v1/posts/categories/{category}/all"
    try:
        response = await client.get(url, params={"page": 1, "limit": limit}, timeout=12.0)
        response.raise_for_status()
        posts = _unwrap_posts(response.json())
    except Exception as exc:
        logger.warning("Knowledge feed fetch failed for %s: %s", category, exc)
        return []
    normalized: list[dict[str, Any]] = []
    for post in posts:
        row = normalize_knowledge_post(post, fallback_category=category)
        if row:
            normalized.append(row)
    return normalized


async def fetch_knowledge_feed_pool(*, limit_per_category: int | None = None) -> list[dict[str, Any]]:
    if not hl_settings.KNOWLEDGE_FEED_ENABLED:
        return []

    limit = limit_per_category or hl_settings.KNOWLEDGE_FEED_FETCH_LIMIT
    cache_key = f"pool:{limit}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < hl_settings.KNOWLEDGE_FEED_CACHE_TTL:
        return list(cached[1])

    pool: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for category in _KNOWLEDGE_CATEGORIES:
            pool.extend(await _fetch_category(client, category, limit=limit))

    _CACHE[cache_key] = (now, pool)
    return pool


def clear_knowledge_feed_cache() -> None:
    _CACHE.clear()
