"""Build-time validation gates per HLHP Engine Implementation Spec v2 §14."""

from __future__ import annotations

from typing import Any

from app.hlhp.evidence.models import INTERNAL_SCIENCE_MARKER, EvidenceFinding
from app.hlhp.evidence.voice import validate_l1_voice

VALID_MOOD_TAGS = {
    "easy_day",
    "comfortable_day",
    "manageable_day",
    "stack_day",
    "barrier_stress_day",
    "pigment_overdrive_day",
    "sebum_rush_day",
    "oxidative_load_day",
    "recovery_day",
    "routine_day",
    "transition_day",
    "cumulative_load_day",
    "habit_anchor_day",
}

VALID_ARCHETYPES = set("ABCDEFGHIJKL")

VALID_TIME_OF_DAY = {"morning_prep", "evening_recovery", "both_phases", "any_time", ""}

VALID_ROUTINE_ACTIONS = {
    "apply_sunscreen",
    "reapply_sunscreen",
    "cleanse_oil",
    "cleanse_gentle",
    "double_cleanse",
    "layer_hydration",
    "layer_barrier",
    "layer_antioxidant",
    "layer_brightening",
    "apply_retinoid_pm",
    "blot",
    "tint_protection",
    "cool_compress",
    "eat_specific_food",
    "take_supplement",
    "improve_sleep",
    "reduce_stress",
    "reduce_smoking",
    "reduce_alcohol",
    "consult_dermatologist",
    "no_action_needed",
}

VALID_ICON_HINTS = {
    "sun",
    "cloud_sun",
    "wind",
    "droplet",
    "flame",
    "snowflake",
    "smog",
    "night_moon",
    "moon_zz",
    "wave",
    "leaf",
    "pill",
    "fork_knife",
    "heart",
    "shield",
    "mirror",
    "scissor",
    "mood",
}

_EVENING_PHASES = {"evening_recovery", "both_phases"}


def validate_engagement_metadata(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for row in rows:
        if row.get("never_fire") or row.get("internal_only"):
            continue
        priority = (row.get("priority") or "").upper()
        if priority != "P0":
            continue
        row_id = row["id"]
        mood = (row.get("mood_verdict_tag") or "").strip()
        archetype = (row.get("engagement_archetype") or "").strip().upper()
        routine = (row.get("routine_action") or "").strip()
        icon = (row.get("visual_icon_hint") or "").strip()
        phase = (row.get("time_of_day_phase") or "").strip()

        if mood and mood not in VALID_MOOD_TAGS:
            issues.append(
                {"row_id": row_id, "rule": "mood_verdict_tag", "detail": f"invalid '{mood}'"}
            )
        if not mood:
            issues.append({"row_id": row_id, "rule": "mood_verdict_tag", "detail": "missing on P0"})
        if archetype and archetype not in VALID_ARCHETYPES:
            issues.append(
                {"row_id": row_id, "rule": "engagement_archetype", "detail": f"invalid '{archetype}'"}
            )
        if not archetype:
            issues.append(
                {"row_id": row_id, "rule": "engagement_archetype", "detail": "missing on P0"}
            )
        if routine and routine not in VALID_ROUTINE_ACTIONS:
            issues.append(
                {"row_id": row_id, "rule": "routine_action", "detail": f"invalid '{routine}'"}
            )
        if not routine:
            issues.append({"row_id": row_id, "rule": "routine_action", "detail": "missing on P0"})
        if icon and icon not in VALID_ICON_HINTS:
            issues.append(
                {"row_id": row_id, "rule": "visual_icon_hint", "detail": f"invalid '{icon}'"}
            )
        if not icon:
            issues.append(
                {"row_id": row_id, "rule": "visual_icon_hint", "detail": "missing on P0"}
            )
        if phase not in VALID_TIME_OF_DAY:
            issues.append(
                {"row_id": row_id, "rule": "time_of_day_phase", "detail": f"invalid '{phase}'"}
            )
        if not phase:
            issues.append(
                {"row_id": row_id, "rule": "time_of_day_phase", "detail": "missing on P0"}
            )
    return issues


def validate_evening_variants(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for row in rows:
        if row.get("never_fire") or row.get("internal_only"):
            continue
        phase = (row.get("time_of_day_phase") or "").strip()
        if phase not in _EVENING_PHASES:
            continue
        row_id = row["id"]
        if not (row.get("alert_l1_evening_personalised") or "").strip():
            issues.append(
                {
                    "row_id": row_id,
                    "rule": "evening_l1",
                    "detail": "missing alert_l1_evening_personalised",
                }
            )
        if not (row.get("alert_l1_evening_guest") or "").strip():
            issues.append(
                {
                    "row_id": row_id,
                    "rule": "evening_l1",
                    "detail": "missing alert_l1_evening_guest",
                }
            )
    return issues


def validate_snapshot_v2(
    rows: list[dict[str, Any]],
    glossary: list[dict[str, Any]],
    book_inventory: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Aggregate all build gates; returns list of failures."""
    from app.hlhp.evidence.citations import validate_citations

    failures: list[dict[str, str]] = []
    failures.extend(validate_l1_voice(rows, glossary))
    failures.extend(validate_citations(rows, book_inventory))
    failures.extend(validate_engagement_metadata(rows))
    failures.extend(validate_evening_variants(rows))
    return failures


def findings_from_rows(rows: list[dict[str, Any]]) -> list[EvidenceFinding]:
    return [EvidenceFinding.from_dict(r) for r in rows]
