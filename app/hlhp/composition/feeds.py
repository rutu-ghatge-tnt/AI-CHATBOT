"""Load festival + seasonal transition JSON feeds."""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

_FEEDS_DIR = Path(__file__).resolve().parents[1] / "data" / "feeds"


@lru_cache(maxsize=1)
def load_festival_calendar() -> dict:
    path = _FEEDS_DIR / "festival_calendar_india_2026.json"
    if not path.exists():
        return {"festivals": []}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_seasonal_transitions() -> dict:
    path = _FEEDS_DIR / "seasonal_transitions_india.json"
    if not path.exists():
        return {"cities": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _fest_date(fest: dict[str, Any]) -> date | None:
    try:
        return datetime.fromisoformat(str(fest["date"])).date()
    except (KeyError, ValueError, TypeError):
        return None


def _skin_festivals() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fest in load_festival_calendar().get("festivals") or []:
        if fest.get("skin_relevant") is False:
            continue
        if not fest.get("skin_impacts") and not fest.get("tags"):
            continue
        if _fest_date(fest) is None:
            continue
        out.append(fest)
    return out


def days_until_festival(fest: dict[str, Any], when: date) -> int | None:
    fdate = _fest_date(fest)
    if fdate is None:
        return None
    return (fdate - when).days


def upcoming_skin_festivals(
    when: datetime | date | None = None,
    *,
    prep_window_days: int = 14,
) -> list[dict[str, Any]]:
    """Festivals in the prep window (today through N days ahead), skin-relevant only."""
    anchor = when.date() if isinstance(when, datetime) else (when or date.today())
    matches: list[tuple[int, dict[str, Any]]] = []
    for fest in _skin_festivals():
        days = days_until_festival(fest, anchor)
        if days is None:
            continue
        window = int(fest.get("prep_window_days") or prep_window_days)
        if 0 <= days <= window:
            matches.append((days, fest))
    matches.sort(key=lambda item: item[0])
    return [fest for _, fest in matches]


def festival_on_date(when: datetime | date | None = None) -> dict[str, Any] | None:
    anchor = when.date() if isinstance(when, datetime) else (when or date.today())
    for fest in _skin_festivals():
        fdate = _fest_date(fest)
        if fdate == anchor:
            return fest
    return None


def nearest_skin_festival_prep(
    when: datetime | date | None = None,
) -> dict[str, Any] | None:
    upcoming = upcoming_skin_festivals(when)
    return upcoming[0] if upcoming else None


def festival_situation_tags(when: datetime | date | None = None) -> list[str]:
    """Tags for explore nugget ranking — prep window + festival day."""
    anchor = when or datetime.now()
    tags: list[str] = []
    today_fest = festival_on_date(anchor)
    if today_fest:
        tags.append("festival_day")
        tags.extend(str(t) for t in (today_fest.get("skin_impacts") or today_fest.get("tags") or []))
    for fest in upcoming_skin_festivals(anchor):
        tags.extend(str(t) for t in (fest.get("skin_impacts") or []))
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return ordered


def seasonal_tags_for_city(city: str, when: datetime | None = None) -> list[str]:
    data = load_seasonal_transitions()
    when = when or datetime.now()
    month = when.strftime("%b")
    cities = data.get("cities") or {}
    entries = cities.get(city) or cities.get("default") or []
    tags: list[str] = []
    for entry in entries:
        window = str(entry.get("window") or "")
        if month in window or any(m in window for m in (month, when.strftime("%B"))):
            tag = entry.get("tag")
            if tag:
                tags.append(str(tag))
    return tags


def festival_tags(when: datetime | None = None, *, window_days: int = 7) -> list[str]:
    """Legacy helper — tags for festivals within ±window_days (skin-relevant only)."""
    when = when or datetime.now()
    anchor = when.date()
    tags: list[str] = []
    for fest in _skin_festivals():
        days = days_until_festival(fest, anchor)
        if days is None or abs(days) > window_days:
            continue
        tags.extend(str(t) for t in (fest.get("tags") or []))
        name = fest.get("name")
        if name:
            tags.append(str(name))
    return tags
