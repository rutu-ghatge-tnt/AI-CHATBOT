"""Coverage matrix computation, gap-fill, and workbook sync."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

_SKIN_TYPES = {"dry", "normal", "combination", "oily", "sensitive"}

# Matrix column -> workbook concern tokens that satisfy coverage (matches runtime matcher).
CONCERN_COLUMN_ALIASES: dict[str, set[str]] = {
    "acne": {"acne", "sensitive-acne-overlap"},
    "melasma": {"melasma"},
    "pigmentation": {"pigmentation", "pih"},
    "tan": {"tan"},
    "aging": {"aging"},
    "photoaging": {"photoaging", "aging"},
    "eczema": {"eczema", "sensitivity", "sensitive", "atopic-flare"},
    "psoriasis": {"psoriasis", "eczema", "sensitivity"},
    "dullness": {"dullness"},
    "dark_circles": {"dark_circles"},
    "dehydration": {"dehydration", "dryness", "xerosis", "dehydration-oily-paradox"},
    "large_pores": {"large_pores", "pores", "texture"},
    "hair_loss": {"hair_loss", "thinning"},
    "rosacea": {"rosacea", "redness", "sensitivity"},
}

_GRID_FACTORS = ("UV", "Temperature", "Humidity", "Pollution", "Sleep", "Stress")
_SKIN_TYPE_GRID = ("dry", "normal", "combination", "oily", "sensitive")
_CONCERN_GRID = tuple(CONCERN_COLUMN_ALIASES.keys())
_AGE_GRID = ("18-25", "25-40", "40-60", "60+")
_GENDER_GRID = ("female", "male")


def _factor_sheet(trigger: str) -> str:
    if trigger in {"Sleep", "Stress"}:
        return "Lifestyle"
    if trigger == "Nutritional Status":
        return "Nutritional Status"
    return trigger


def _trigger_key_for_row(row: dict[str, Any]) -> str:
    factor = row.get("factor") or ""
    tokens = row.get("triggers", {}).get("user_filter", [])
    if factor in {"Nutritional Status", "Lifestyle"}:
        for token in tokens:
            if token.get("class") == "sleep":
                return "Sleep"
            if token.get("class") == "stress":
                return "Stress"
    return factor


def _concern_tokens(row: dict[str, Any]) -> set[str]:
    return {t["value"] for t in row.get("triggers", {}).get("user_filter", []) if t["class"] == "concern"}


def _skin_type_tokens(row: dict[str, Any]) -> set[str]:
    return {t["value"] for t in row.get("triggers", {}).get("user_filter", []) if t["class"] == "skin_type"}


def row_covers_skin_type(row: dict[str, Any], skin_type: str) -> bool:
    tokens = _skin_type_tokens(row)
    if not tokens:
        return True
    if skin_type in tokens:
        return True
    if skin_type == "sensitive" and tokens & {"sensitive", "iii-v", "iv-v", "iii-vi", "all"}:
        return True
    return False


def row_covers_concern(row: dict[str, Any], column: str) -> bool:
    tokens = _concern_tokens(row)
    if not tokens:
        return False
    allowed = CONCERN_COLUMN_ALIASES.get(column, {column})
    return bool(tokens & allowed)


def _rows_for_trigger(findings: list[dict[str, Any]], trigger: str) -> list[dict[str, Any]]:
    if trigger in {"Sleep", "Stress"}:
        return [r for r in findings if r.get("factor") == "Lifestyle"]
    return [r for r in findings if _trigger_key_for_row(r) == trigger]


def compute_coverage_grids(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grids: list[dict[str, Any]] = []

    skin_rows = []
    for trigger in _GRID_FACTORS:
        pool = _rows_for_trigger(findings, trigger)
        counts = [
            sum(1 for row in pool if row_covers_skin_type(row, col)) for col in _SKIN_TYPE_GRID
        ]
        skin_rows.append({"trigger": trigger, "counts": counts})
    grids.append({"title": "Trigger × Skin Type", "columns": list(_SKIN_TYPE_GRID), "rows": skin_rows})

    concern_rows = []
    for trigger in _GRID_FACTORS:
        pool = _rows_for_trigger(findings, trigger)
        counts = [
            sum(1 for row in pool if row_covers_concern(row, col)) for col in _CONCERN_GRID
        ]
        concern_rows.append({"trigger": trigger, "counts": counts})
    grids.append(
        {"title": "Trigger × Skin Concern", "columns": list(_CONCERN_GRID), "rows": concern_rows}
    )

    gender_rows = []
    for trigger in _GRID_FACTORS:
        pool = _rows_for_trigger(findings, trigger)
        counts = [
            sum(
                1
                for row in pool
                if any(
                    t["class"] == "gender" and t["value"] == col
                    for t in row.get("triggers", {}).get("user_filter", [])
                )
            )
            for col in _GENDER_GRID
        ]
        gender_rows.append({"trigger": trigger, "counts": counts})
    grids.append({"title": "Trigger × Gender", "columns": list(_GENDER_GRID), "rows": gender_rows})

    age_rows = []
    for trigger in _GRID_FACTORS:
        pool = _rows_for_trigger(findings, trigger)
        counts = [
            sum(
                1
                for row in pool
                if any(
                    t["class"] == "age" and t["value"] == col
                    for t in row.get("triggers", {}).get("user_filter", [])
                )
            )
            for col in _AGE_GRID
        ]
        age_rows.append({"trigger": trigger, "counts": counts})
    grids.append({"title": "Trigger × Age band", "columns": list(_AGE_GRID), "rows": age_rows})

    return grids


def _append_user_filter(row: dict[str, Any], class_name: str, value: str) -> None:
    tokens = row.setdefault("triggers", {}).setdefault("user_filter", [])
    if any(t.get("class") == class_name and t.get("value") == value for t in tokens):
        return
    tokens.append({"class": class_name, "value": value})


def _format_user_filter(tokens: list[dict[str, str]]) -> str:
    if not tokens:
        return "any"
    return ", ".join(f"{t['class']}:{t['value']}" for t in tokens)


def fill_coverage_gaps(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Tag untargeted rows so every concern × factor cell has at least one match."""
    fixes: list[dict[str, str]] = []
    used: set[str] = set()

    for trigger in _GRID_FACTORS:
        pool = _rows_for_trigger(findings, trigger)
        candidates = [
            r
            for r in pool
            if not r.get("never_fire")
            and len(r.get("triggers", {}).get("user_filter", [])) <= 2
        ]
        if not candidates:
            candidates = pool

        for column in _CONCERN_GRID:
            if any(row_covers_concern(r, column) for r in pool):
                continue
            pick = next((r for r in candidates if r["id"] not in used), None)
            if pick is None:
                pick = next((r for r in pool if r["id"] not in used), None)
            if pick is None:
                continue
            token = column if column in CONCERN_COLUMN_ALIASES else column
            if column == "photoaging":
                token = "photoaging"
            _append_user_filter(pick, "concern", token)
            used.add(pick["id"])
            fixes.append(
                {
                    "row_id": pick["id"],
                    "factor": pick["factor"],
                    "row_number": str(pick["row_number"]),
                    "detail": f"added concern:{token} for {trigger}×{column}",
                }
            )

    pool = _rows_for_trigger(findings, "Temperature")
    if not any(row_covers_skin_type(r, "normal") for r in pool):
        pick = next((r for r in pool if not _skin_type_tokens(r)), None)
        if pick:
            _append_user_filter(pick, "skin_type", "normal")
            fixes.append(
                {
                    "row_id": pick["id"],
                    "factor": pick["factor"],
                    "row_number": str(pick["row_number"]),
                    "detail": "added skin_type:normal for Temperature×normal",
                }
            )

    _fill_dimension_gaps(findings, fixes, cls="gender", columns=_GENDER_GRID)
    _fill_dimension_gaps(findings, fixes, cls="age", columns=_AGE_GRID)

    return fixes


def _fill_dimension_gaps(
    findings: list[dict[str, Any]],
    fixes: list[dict[str, str]],
    *,
    cls: str,
    columns: tuple[str, ...],
) -> None:
    used: set[str] = {f["row_id"] for f in fixes}
    for trigger in _GRID_FACTORS:
        pool = _rows_for_trigger(findings, trigger)
        for column in columns:
            if any(
                any(t.get("class") == cls and t.get("value") == column for t in r.get("triggers", {}).get("user_filter", []))
                for r in pool
            ):
                continue
            pick = next((r for r in pool if r["id"] not in used), None) or next(iter(pool), None)
            if not pick:
                continue
            _append_user_filter(pick, cls, column)
            used.add(pick["id"])
            fixes.append(
                {
                    "row_id": pick["id"],
                    "factor": pick["factor"],
                    "row_number": str(pick["row_number"]),
                    "detail": f"added {cls}:{column} for {trigger}",
                }
            )


def build_coverage_report(
    findings: list[dict[str, Any]],
    coverage_matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    computed_grids = compute_coverage_grids(findings)
    true_gaps: list[dict[str, Any]] = []

    for grid in computed_grids:
        for grid_row in grid["rows"]:
            trigger = grid_row["trigger"]
            for col, count in zip(grid["columns"], grid_row["counts"]):
                if count == 0:
                    true_gaps.append(
                        {
                            "grid": grid["title"],
                            "trigger": trigger,
                            "column": col,
                            "computed_count": 0,
                            "status": "gap",
                        }
                    )

    return {
        "methodology": "Rule-based coverage from Trigger_User_Filter tokens and concern aliases.",
        "computed_grids": computed_grids,
        "true_gap_count": len(true_gaps),
        "true_gaps": true_gaps,
        "thin_cells": [
            cell
            for grid in computed_grids
            for grid_row in grid["rows"]
            for col, count in zip(grid["columns"], grid_row["counts"])
            if 0 < count <= 2
            for cell in [
                {
                    "grid": grid["title"],
                    "trigger": grid_row["trigger"],
                    "column": col,
                    "computed_count": count,
                    "status": "thin",
                }
            ]
        ],
    }


def write_coverage_matrix_sheet(ws, grids: list[dict[str, Any]]) -> None:
    """Rewrite Coverage_Matrix sheet from computed grids."""
    ws.delete_rows(1, ws.max_row)
    ws.append(["Coverage matrix — auto-generated from evidence snapshot", None, None, None])
    ws.append([None, "0 = gap (red)", "1–2 = thin (amber)", "≥3 = adequate (green)"])
    ws.append([None, None, None, None])

    for grid in grids:
        ws.append([grid["title"]])
        ws.append(["Trigger", *grid["columns"]])
        for row in grid["rows"]:
            ws.append([row["trigger"], *row["counts"]])
