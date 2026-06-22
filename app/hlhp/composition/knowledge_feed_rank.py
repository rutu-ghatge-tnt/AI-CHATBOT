"""Rank Knowledge Feed posts for HLHP Explore by concern + situation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.hlhp.models.profile import UserProfile

from app.hlhp.composition.feeds import festival_situation_tags
from app.hlhp.core.bands import EnvironmentBands, science_condition_tags
from app.hlhp.services.concern_resolver import profile_concern_slugs

_TAG_MAP_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_feed_tag_map.json"

_CATEGORY_PRIORITY = ("skinvestigators", "stories", "jargons")


@lru_cache(maxsize=1)
def _load_tag_map() -> dict[str, Any]:
    if not _TAG_MAP_PATH.exists():
        return {}
    return json.loads(_TAG_MAP_PATH.read_text(encoding="utf-8"))


def situation_tags_for_explore(
    *,
    bands: EnvironmentBands | None,
    when: datetime,
) -> list[str]:
    tags = list(festival_situation_tags(when))
    if bands is not None:
        tags.extend(science_condition_tags(bands))
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return ordered


def _blob(post: dict[str, Any]) -> str:
    parts = [
        str(post.get("title") or ""),
        str(post.get("excerpt") or ""),
        " ".join(post.get("tag_slugs") or []),
    ]
    return " ".join(parts).lower()


def _concern_slugs(
    concern_id: str | None,
    profile: UserProfile | None = None,
) -> frozenset[str]:
    return profile_concern_slugs(profile, fallback_concern_id=concern_id)


def _keyword_hits(blob: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for word in keywords if word in blob)


def _score_post(
    post: dict[str, Any],
    *,
    concern_slugs: frozenset[str],
    situation_tags: list[str],
) -> tuple[int, list[str]]:
    tag_map = _load_tag_map()
    blob = _blob(post)
    score = 0
    reasons: list[str] = []

    concern_keywords: dict[str, list[str]] = tag_map.get("concern_keywords") or {}
    for concern in concern_slugs:
        hits = _keyword_hits(blob, tuple(concern_keywords.get(concern, ())))
        if hits:
            score += min(3, hits) * 2
            reasons.append(f"matches {concern.replace('_', ' ')}")

    tag_to_concerns: dict[str, list[str]] = tag_map.get("tag_to_concerns") or {}
    for tag in post.get("tag_slugs") or []:
        mapped = tag_to_concerns.get(tag) or tag_to_concerns.get(tag.replace("_", "-"))
        if mapped and concern_slugs.intersection(mapped):
            score += 3
            reasons.append("tagged for your concern")

    situation_keywords: dict[str, list[str]] = tag_map.get("situation_keywords") or {}
    for situation in situation_tags:
        hits = _keyword_hits(blob, tuple(situation_keywords.get(situation, ())))
        if hits:
            score += min(3, hits) * 2
            label = situation.replace("_", " ")
            if label not in reasons:
                reasons.append(f"fits {label}")

    tag_to_situations: dict[str, list[str]] = tag_map.get("tag_to_situations") or {}
    for tag in post.get("tag_slugs") or []:
        mapped = tag_to_situations.get(tag) or tag_to_situations.get(tag.replace("_", "-"))
        if mapped and any(s in situation_tags for s in mapped):
            score += 2
            reasons.append("tagged for today")

    return score, reasons[:2]


def _stable_offset(*, user_id: str | None, when: datetime, pool_size: int) -> int:
    if pool_size <= 0:
        return 0
    key = f"{user_id or 'guest'}:{when.date().isoformat()}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    return int(digest[:8], 16) % pool_size


def rank_knowledge_feed_posts(
    posts: list[dict[str, Any]],
    *,
    concern_id: str | None,
    bands: EnvironmentBands | None,
    when: datetime,
    user_id: str | None = None,
    profile: UserProfile | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not posts:
        return []

    concern_slugs = _concern_slugs(concern_id, profile)
    situations = situation_tags_for_explore(bands=bands, when=when)

    scored: list[tuple[int, str, dict[str, Any], list[str]]] = []
    for post in posts:
        score, reasons = _score_post(post, concern_slugs=concern_slugs, situation_tags=situations)
        scored.append((score, str(post.get("slug") or ""), post, reasons))

    scored.sort(key=lambda item: (-item[0], item[1]))

    if not concern_slugs and not situations:
        offset = _stable_offset(user_id=user_id, when=when, pool_size=len(scored))
        rotated = scored[offset:] + scored[:offset]
        scored = rotated

    picked: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    used_categories: set[str] = set()

    def _append(entry: tuple[int, str, dict[str, Any], list[str]]) -> None:
        _score, _slug, post, reasons = entry
        slug = str(post.get("slug") or "")
        if slug in used_slugs:
            return
        used_slugs.add(slug)
        used_categories.add(str(post.get("category_slug") or ""))
        match_reason = reasons[0] if reasons else "picked for you"
        picked.append({**post, "match_score": _score, "match_reason": match_reason})

    for category in _CATEGORY_PRIORITY:
        if len(picked) >= limit:
            break
        for entry in scored:
            if str(entry[2].get("category_slug") or "") == category:
                _append(entry)
                break

    for entry in scored:
        if len(picked) >= limit:
            break
        _append(entry)

    return picked[:limit]
