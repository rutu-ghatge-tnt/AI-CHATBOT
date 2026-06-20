from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.hlhp.evidence.models import EvidenceFinding


def filter_by_recency(
    candidates: list[EvidenceFinding],
    suppressed_rule_ids: set[str],
) -> list[EvidenceFinding]:
    if not suppressed_rule_ids:
        return candidates
    return [c for c in candidates if c.id not in suppressed_rule_ids]


def prefer_fresh_archetypes(
    ranked: list[tuple],
    recent_archetypes: set[str],
) -> list[tuple]:
    """Deprioritise archetypes shown in the last few days."""

    def sort_key(item: tuple) -> tuple:
        finding, score, matched = item
        archetype = (finding.engagement_archetype or "").upper()
        penalty = 1 if archetype and archetype in recent_archetypes else 0
        return (penalty, -score, finding.row_number)

    return sorted(ranked, key=sort_key)
