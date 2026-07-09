"""Assemble concern deep-dive pages from composition snapshot."""

from __future__ import annotations

from typing import Any, Optional

from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.evidence.composition_store import get_composition_store


def _filter_rows(rows: list[dict], concern_id: str, key: str = "concern_id") -> list[dict]:
    cid = concern_id.strip().lower()
    return [r for r in rows if str(r.get(key, "")).strip().lower() == cid]


def assemble_concern_deepdive(concern_id: str) -> Optional[dict[str, Any]]:
    store = get_composition_store()
    comp = store.composition
    pages = comp.get("concern_pages") or []
    page = next(
        (p for p in pages if str(p.get("concern_id", "")).strip().lower() == concern_id.lower()),
        None,
    )
    if not page:
        return None

    drivers = sorted(
        _filter_rows(comp.get("concern_drivers") or [], concern_id),
        key=lambda r: int(r.get("driver_order") or 0),
    )
    routine = sorted(
        _filter_rows(comp.get("concern_routine_framework") or [], concern_id),
        key=lambda r: (str(r.get("phase") or ""), int(r.get("step_order") or 0)),
    )
    myths = sorted(
        _filter_rows(comp.get("concern_myths") or [], concern_id),
        key=lambda r: int(r.get("myth_order") or 0),
    )
    timeline = sorted(
        _filter_rows(comp.get("concern_timeline") or [], concern_id),
        key=lambda r: int(r.get("phase_order") or 0),
    )
    triage = sorted(
        _filter_rows(comp.get("concern_dermatologist_triage") or [], concern_id),
        key=lambda r: int(r.get("triage_order") or 0),
    )

    mood_pills_raw = str(page.get("mood_pills") or "")
    mood_pills = [p.strip() for p in mood_pills_raw.replace(";", ",").split(",") if p.strip()]

    morning_steps = [r for r in routine if str(r.get("phase", "")).lower() == "morning"]
    evening_steps = [r for r in routine if str(r.get("phase", "")).lower() == "evening"]

    return {
        "concern_id": page.get("concern_id"),
        "display_name": page.get("concern_display_name"),
        "hero_title": page.get("hero_title"),
        "hero_sub": page.get("hero_sub"),
        "mood_pills": mood_pills,
        "drivers": drivers,
        "routine_morning": morning_steps,
        "routine_evening": evening_steps,
        "myths": myths,
        "timeline": timeline,
        "dermatologist_triage": [
            {
                "trigger": r.get("escalation_trigger"),
                "urgency": r.get("urgency_band"),
            }
            for r in triage
        ],
        "snapshot_version": store.version,
        "workbook_version": store.workbook_version,
    }
