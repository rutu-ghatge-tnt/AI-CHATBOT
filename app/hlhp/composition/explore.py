"""Event guides + explore lane assembly."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.hlhp.composition.vocabulary import symptom_chips
from app.hlhp.evidence.loader import get_evidence_store


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


def assemble_explore(city: str, concern_id: str | None = None) -> dict[str, Any]:
    store = get_evidence_store()
    guides = assemble_event_guides(city)[:4]
    nuggets = store.composition.get("daily_nuggets_rotation") or []
    nugget = nuggets[0] if nuggets else None
    return {
        "city": city,
        "event_guides": guides,
        "science_nugget": {
            "text": (nugget or {}).get("nugget_text"),
            "category": (nugget or {}).get("nugget_category"),
        }
        if nugget
        else None,
        "symptom_keywords": symptom_chips(concern_id),
        "snapshot_version": store.workbook_version,
    }
