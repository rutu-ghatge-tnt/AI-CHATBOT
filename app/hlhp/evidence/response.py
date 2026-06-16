"""Map evidence bundle → API response fields."""

from __future__ import annotations

from app.hlhp.evidence.models import EvidenceBundle
from app.hlhp.models.alert import (
    CoverageThinCell,
    EvidenceAlertCard,
    GapConflictCard,
    ScienceNuggetCard,
)


def evidence_cards(bundle: EvidenceBundle | None) -> dict:
    if not bundle:
        return {
            "evidence_version": None,
            "evidence_primary_id": None,
            "evidence_carousel": None,
            "habit_alerts": None,
            "science_nuggets": None,
            "clinical_gaps": None,
            "coverage_thin_cells": None,
        }
    return {
        "evidence_version": bundle.evidence_version,
        "evidence_primary_id": bundle.primary.finding.id if bundle.primary else None,
        "evidence_carousel": [EvidenceAlertCard(**c.__dict__) for c in bundle.carousel] or None,
        "habit_alerts": [EvidenceAlertCard(**c.__dict__) for c in bundle.habit_alerts] or None,
        "science_nuggets": [ScienceNuggetCard(**n.__dict__) for n in bundle.science_nuggets]
        or None,
        "clinical_gaps": [GapConflictCard(**g.__dict__) for g in bundle.gaps_conflicts] or None,
        "coverage_thin_cells": [CoverageThinCell(**c) for c in bundle.coverage_thin_cells]
        or None,
    }
