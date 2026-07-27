"""Fetch published SkinBB blogs for HLHP Learn / Explore."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.hlhp.config import hl_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _unwrap_blogs(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("blogs"), list):
        return [b for b in data["blogs"] if isinstance(b, dict)]
    if isinstance(data, list):
        return [b for b in data if isinstance(b, dict)]
    if isinstance(payload.get("blogs"), list):
        return [b for b in payload["blogs"] if isinstance(b, dict)]
    return []


def _image_url(node: Any) -> str | None:
    if isinstance(node, dict):
        url = node.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    if isinstance(node, str) and node.strip():
        return node.strip()
    return None


def _strip_html(value: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _slugify_tag(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-")


def _tag_slugs(blog: dict[str, Any]) -> list[str]:
    raw = blog.get("tag")
    if raw is None:
        raw = blog.get("tags") or blog.get("tagIds") or []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        slug = ""
        if isinstance(item, dict):
            for key in ("slug", "name"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    slug = _slugify_tag(val)
                    break
        elif isinstance(item, str) and item.strip():
            slug = _slugify_tag(item)
        if slug and slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out


def _category_slug(blog: dict[str, Any]) -> str:
    categories = blog.get("categories")
    if isinstance(categories, list):
        for item in categories:
            if isinstance(item, dict):
                slug = item.get("slug")
                if isinstance(slug, str) and slug.strip():
                    return slug.strip().lower()
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    return _slugify_tag(name)
            elif isinstance(item, str) and item.strip():
                return _slugify_tag(item)
    return "blogs"


def normalize_blog_post(blog: dict[str, Any]) -> dict[str, Any] | None:
    status = str(blog.get("status") or "published").strip().lower()
    if status and status != "published":
        return None
    if blog.get("isDeleted") is True:
        return None

    slug = str(blog.get("slug") or "").strip()
    title = _strip_html(str(blog.get("title") or "").strip())
    if not slug or not title:
        return None

    raw_excerpt = str(blog.get("description") or "").strip()
    if not raw_excerpt and isinstance(blog.get("seo"), dict):
        raw_excerpt = str(blog["seo"].get("metaDescription") or "").strip()
    if not raw_excerpt:
        raw_excerpt = str(blog.get("content") or "").strip()

    excerpt = _strip_html(raw_excerpt)[:280]
    thumbnail = (
        _image_url(blog.get("featuredImage"))
        or _image_url(blog.get("image"))
        or _image_url((blog.get("seo") or {}).get("image") if isinstance(blog.get("seo"), dict) else None)
    )

    return {
        "post_id": str(blog.get("_id") or slug),
        "slug": slug,
        "category_slug": _category_slug(blog),
        "content_type": "Blog",
        "title": title,
        "excerpt": excerpt,
        "thumbnail_url": thumbnail,
        "tag_slugs": _tag_slugs(blog),
        "read_time": blog.get("readTime") or blog.get("read_time"),
        "published_at": str(blog.get("publishedDate") or blog.get("publishedAt") or "") or None,
    }


async def fetch_blog_feed_pool(*, limit: int | None = None) -> list[dict[str, Any]]:
    if not hl_settings.BLOG_FEED_ENABLED:
        return []

    fetch_limit = limit or hl_settings.BLOG_FEED_FETCH_LIMIT
    cache_key = f"blogs:{fetch_limit}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < hl_settings.BLOG_FEED_CACHE_TTL:
        return list(cached[1])

    url = f"{hl_settings.SKINBB_API_BASE_URL}/api/v1/blogs"
    pool: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"page": 1, "limit": fetch_limit, "status": "published"},
                timeout=12.0,
            )
            response.raise_for_status()
            blogs = _unwrap_blogs(response.json())
    except Exception as exc:
        logger.warning("Blog feed fetch failed: %s", exc)
        return []

    for blog in blogs:
        row = normalize_blog_post(blog)
        if row:
            pool.append(row)

    _CACHE[cache_key] = (now, pool)
    return pool


def clear_blog_feed_cache() -> None:
    _CACHE.clear()
