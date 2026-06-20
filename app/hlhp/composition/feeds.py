"""Load festival + seasonal transition JSON feeds."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

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
    cal = load_festival_calendar()
    when = when or datetime.now()
    tags: list[str] = []
    for fest in cal.get("festivals") or []:
        try:
            fdate = datetime.fromisoformat(str(fest["date"]))
        except (KeyError, ValueError):
            continue
        if abs((fdate.date() - when.date()).days) <= window_days:
            tags.extend(fest.get("tags") or [])
            name = fest.get("name")
            if name:
                tags.append(str(name))
    return tags
