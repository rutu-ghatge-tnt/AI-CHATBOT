"""Resolve lane nav CTA strings from Lane_State_Strings."""

from __future__ import annotations

from typing import Any

from app.hlhp.evidence.loader import get_evidence_store

_DEFAULT_CTAS = {
    "today": "Check today's alerts",
    "your_skin": "7-day forecast",
    "explore": "12 guides + nuggets",
    "history": "Last 30 days",
}


def resolve_lane_states(*, alert_count: int = 0, sudden_event: bool = False) -> dict[str, str]:
    store = get_evidence_store()
    rows = store.composition.get("lane_state_strings") or []
    out = dict(_DEFAULT_CTAS)

    ranked: list[tuple[int, str, str]] = []
    for row in rows:
        lane = str(row.get("lane_id") or "").strip().lower()
        cta = str(row.get("cta_text") or "").strip()
        if not lane or not cta:
            continue
        try:
            priority = int(row.get("priority") or 0)
        except (TypeError, ValueError):
            priority = 0
        ranked.append((priority, lane, cta))

    for _pri, lane, cta in sorted(ranked, key=lambda x: -x[0]):
        if lane in out:
            out[lane] = cta

    if alert_count > 0:
        out["today"] = f"{alert_count} alerts ready"
    if sudden_event:
        out["today"] = out.get("today", "Sudden event detected")

    return out
