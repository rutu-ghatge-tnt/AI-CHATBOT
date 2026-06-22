"""Read Layer 2 composition sheets from HLHP_Evidence_Base.xlsx."""

from __future__ import annotations

import re
from typing import Any

_LEGEND_MARKERS = (
    "slug",
    "fk to",
    "user-facing",
    "placeholder",
    "meaning",
    "streak stages",
    "1–",
    "1-",
    "comma-separated",
    "y / n",
    "morning / evening",
    "40–",
    "≤",
)


def _norm_header(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_legend_row(first_cell: object) -> bool:
    if first_cell is None:
        return True
    text = str(first_cell).strip().lower()
    if not text:
        return True
    if text in {"easy_day", "comfortable_day"} and len(text) < 30:
        # Coach sheet section headers without template_id
        return "template" not in text and not text.startswith("cv-")
    return any(m in text for m in _LEGEND_MARKERS)


def _cell_val(row: tuple, idx: int) -> Any:
    if idx >= len(row):
        return None
    val = row[idx]
    if isinstance(val, str):
        return val.strip()
    return val


def read_composition_table(ws, *, header_row: int | None = None) -> list[dict[str, Any]]:
    """Read a composition sheet: locate header row, skip legend rows, emit dicts."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    hdr_idx = header_row
    if hdr_idx is None:
        for i, row in enumerate(rows[:30]):
            if not row or not row[0]:
                continue
            first = _norm_header(row[0])
            if first and re.match(r"^[a-z][a-z0-9_]+$", first):
                hdr_idx = i
                break
    if hdr_idx is None:
        return []

    headers = [_norm_header(h) for h in rows[hdr_idx]]
    col_map = {h: i for i, h in enumerate(headers) if h}
    out: list[dict[str, Any]] = []

    for row in rows[hdr_idx + 1 :]:
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue
        if _is_legend_row(row[0]):
            continue
        record = {h: _cell_val(row, i) for h, i in col_map.items()}
        if not any(v not in (None, "") for v in record.values()):
            continue
        out.append(record)
    return out


def read_all_composition(wb) -> dict[str, Any]:
    """Export all Layer 2 sheets into a single composition blob."""
    sheet_names = {
        "concern_pages": "Concern_Pages",
        "concern_drivers": "Concern_Drivers",
        "concern_routine_framework": "Concern_Routine_Framework",
        "concern_myths": "Concern_Myths",
        "concern_timeline": "Concern_Timeline",
        "concern_dermatologist_triage": "Concern_Dermatologist_Triage",
        "event_guides": "Event_Guides",
        "symptom_explainer_pages": "Symptom_Explainer_Pages",
        "daily_nuggets_rotation": "Daily_Nuggets_Rotation",
        "forecast_day_templates": "Forecast_Day_Templates",
        "lane_state_strings": "Lane_State_Strings",
        "coach_voice_templates": "Coach_Voice_Templates",
        "sudden_breakout_alerts": "Sudden_Breakout_Alerts",
        "sudden_event_reuse_map": "Sudden_Event_Reuse_Map",
    }
    composition: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for key, sheet in sheet_names.items():
        if sheet not in wb.sheetnames:
            composition[key] = []
            counts[key] = 0
            continue
        ws = wb[sheet]
        header_row = 21 if key == "coach_voice_templates" else None
        rows = read_composition_table(ws, header_row=header_row)
        composition[key] = rows
        counts[key] = len(rows)
    composition["_counts"] = counts
    return composition
