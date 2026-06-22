"""Event guides + explore lane assembly."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.hlhp.composition.feeds import festival_situation_tags
from app.hlhp.composition.vocabulary import symptom_chips
from app.hlhp.core.bands import EnvironmentBands, science_condition_tags
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.profile import UserProfile
from app.hlhp.services.concern_resolver import (
    nugget_audience_slugs,
    nugget_matches_profile,
    resolve_concern_id,
)

_CATEGORY_DISPLAY = {
    "mechanism": "Did you know?",
    "skin_science": "Did you know?",
    "mythbust": "Myth check",
    "indian_culture": "India context",
}

_SITUATION_NUGGET_HINTS: dict[str, tuple[str, ...]] = {
    "festival_day": ("festival", "diwali", "holi", "eid", "sweet"),
    "air_quality_spike": ("pollution", "particulate", "pm2", "aqi", "oxidative", "smog"),
    "diet_shift": ("glycation", "sugar", "diet", "insulin", "sweet", "food"),
    "color_exposure": ("holi", "mehndi", "color", "pigment", "dye"),
    "uv_high": ("uv", "sun", "sunscreen", "spf", "photoag", "visible light", "tan"),
    "temp_high": ("heat", "temperature", "sweat", "sebum", "warm"),
    "aqi_high": ("pollution", "particulate", "pm2", "aqi", "oxidative"),
    "humidity_low": ("dry", "humidity", "dehydr", "barrier", "tewl"),
    "humidity_high": ("humid", "monsoon", "fungal", "muggy", "oil"),
}


def _city_matches(city_scope: str, city: str) -> bool:
    scope = (city_scope or "").lower()
    if not scope or "pan-india" in scope or scope == "any":
        return True
    city_l = city.lower()
    return any(part.strip().lower() in city_l for part in scope.split(",") if part.strip())


def _month_matches(month_window: str, when: datetime) -> bool:
    if not month_window or month_window.lower() == "any":
        return True
    month_abbr = when.strftime("%b").lower()
    month_full = when.strftime("%B").lower()
    parts = [p.strip().lower() for p in month_window.replace(";", ",").split(",")]
    return month_abbr in parts or month_full in parts or any(p in month_abbr for p in parts)


def assemble_event_guides(city: str, when: datetime | None = None) -> list[dict[str, Any]]:
    store = get_evidence_store()
    rows = store.composition.get("event_guides") or []
    now = when or datetime.now()
    by_guide: dict[str, list[dict]] = {}
    for row in rows:
        if not _city_matches(str(row.get("city_scope") or ""), city):
            continue
        if not _month_matches(str(row.get("month_window") or ""), now):
            continue
        gid = str(row.get("guide_id") or row.get("event_anchor") or "")
        by_guide.setdefault(gid, []).append(row)

    guides: list[dict[str, Any]] = []
    for gid, sections in by_guide.items():
        sections = sorted(sections, key=lambda r: int(r.get("section_order") or 0))
        head = sections[0]
        guides.append(
            {
                "guide_id": gid,
                "event_anchor": head.get("event_anchor"),
                "title": head.get("guide_title"),
                "subtitle": head.get("guide_sub"),
                "minutes_to_read": head.get("minutes_to_read"),
                "sections": [
                    {
                        "label": s.get("section_label"),
                        "order": int(s.get("section_order") or 0),
                        "body": s.get("section_body"),
                        "routine_action": s.get("routine_action"),
                    }
                    for s in sections
                ],
            }
        )
    return guides[:12]


def _concern_matches_nugget(row: dict[str, Any], concern_id: str) -> bool:
    audience = str(row.get("concern_audience") or "").lower()
    if not audience or audience == "universal":
        return True
    match_slugs = nugget_audience_slugs(concern_id) or frozenset()
    parts = [p.strip() for p in audience.replace(";", ",").split(",") if p.strip()]
    return any(slug in part or part in slug for slug in match_slugs for part in parts)


def _situation_tags_for_context(
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


def _situation_relevance_score(row: dict[str, Any], situation_tags: list[str]) -> int:
    if not situation_tags:
        return 0
    audience = str(row.get("situation_audience") or "").lower()
    if audience and audience != "any":
        parts = [p.strip() for p in audience.replace(";", ",").split(",") if p.strip()]
        if any(tag in part or part in tag for tag in situation_tags for part in parts):
            return 4
    text = str(row.get("nugget_text") or "").lower()
    score = 0
    for tag in situation_tags:
        for hint in _SITUATION_NUGGET_HINTS.get(tag, ()):
            if hint in text:
                score += 1
    return score


def _pick_daily_nugget(
    rows: list[dict[str, Any]],
    *,
    concern_id: str | None,
    profile: UserProfile | None,
    user_id: str | None,
    when: datetime,
    bands: EnvironmentBands | None = None,
) -> dict[str, Any] | None:
    pool = [
        r
        for r in rows
        if r.get("nugget_text") and nugget_matches_profile(r, profile)
    ]
    if not pool:
        return None
    if concern_id:
        matched = [r for r in pool if _concern_matches_nugget(r, concern_id)]
        if matched:
            pool = matched

    situation_tags = _situation_tags_for_context(bands=bands, when=when)
    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for row in pool:
        env_score = _situation_relevance_score(row, situation_tags)
        priority = int(row.get("priority") or 99)
        nugget_id = str(row.get("nugget_id") or "")
        scored.append((-env_score, priority, nugget_id, row))

    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    best_env_score = scored[0][0]
    tier = [row for neg, *_rest, row in scored if neg == best_env_score]

    key = f"{user_id or 'guest'}:{concern_id or 'any'}:{when.date().isoformat()}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    idx = int(digest[:8], 16) % len(tier)
    return tier[idx]


def _science_nugget_payload(row: dict[str, Any]) -> dict[str, Any]:
    category = str(row.get("nugget_category") or "skin_science")
    return {
        "text": row.get("nugget_text"),
        "category_display": _CATEGORY_DISPLAY.get(category, "Did you know?"),
    }


def assemble_explore(
    city: str,
    concern_id: str | None = None,
    *,
    selected_symptoms: set[str] | None = None,
    user_id: str | None = None,
    profile: UserProfile | None = None,
    when: datetime | None = None,
    bands: EnvironmentBands | None = None,
) -> dict[str, Any]:
    store = get_evidence_store()
    now = when or datetime.now()
    resolved_concern = resolve_concern_id(profile=profile, client_concern_id=concern_id)
    all_guides = assemble_event_guides(city, now)
    guides = all_guides[:4]
    featured = guides[0] if guides else None
    nugget_rows = store.composition.get("daily_nuggets_rotation") or []
    row = _pick_daily_nugget(
        nugget_rows,
        concern_id=resolved_concern,
        profile=profile,
        user_id=user_id,
        when=now,
        bands=bands,
    )
    science_nugget = _science_nugget_payload(row) if row else None
    return {
        "city": city,
        "concern_id": resolved_concern,
        "featured_guide": featured,
        "total_guide_count": len(all_guides),
        "event_guides": guides,
        "science_nugget": science_nugget,
        "knowledge_feed": [],
        "symptom_keywords": symptom_chips(resolved_concern, selected=selected_symptoms or set()),
        "snapshot_version": store.workbook_version,
    }
