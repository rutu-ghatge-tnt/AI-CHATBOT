"""Symptom explainer 4-section pages."""

from __future__ import annotations

from typing import Any, Optional

from app.hlhp.composition.alert_copy import label_routine_action
from app.hlhp.composition.vocabulary import SYMPTOM_RELATIONS
from app.hlhp.evidence.loader import get_evidence_store


def assemble_symptom_explainer(symptom_keyword: str) -> Optional[dict[str, Any]]:
    store = get_evidence_store()
    key = symptom_keyword.strip().lower().replace(" ", "_").replace("-", "_")
    rows = store.composition.get("symptom_explainer_pages") or []
    matched = [
        r
        for r in rows
        if str(r.get("symptom_keyword", "")).strip().lower().replace(" ", "_") == key
    ]
    if not matched:
        return None

    sections = sorted(matched, key=lambda r: int(r.get("section_order") or 0))
    return {
        "symptom_keyword": key,
        "sections": [
            {
                "label": r.get("section_label"),
                "order": int(r.get("section_order") or 0),
                "body": r.get("section_body"),
                "routine_action": r.get("routine_action"),
                "routine_action_label": label_routine_action(str(r.get("routine_action") or "")),
                "source_workbook_rows": r.get("source_workbook_rows"),
            }
            for r in sections
        ],
        "related_symptoms": SYMPTOM_RELATIONS.get(key, []),
        "snapshot_version": store.workbook_version,
        "workbook_version": store.workbook_version,
    }
