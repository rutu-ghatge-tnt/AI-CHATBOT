from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.hlhp.coach.models import CoachTemplate

_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "data" / "coach_templates_v1.json"


def _load_json_templates() -> list[CoachTemplate]:
    if not _TEMPLATES_PATH.exists():
        return []
    raw = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [CoachTemplate.model_validate(row) for row in raw]


def _workbook_to_coach_templates(rows: list[dict[str, Any]]) -> list[CoachTemplate]:
    """Map workbook Coach_Voice_Templates into assembler slot templates."""
    out: list[CoachTemplate] = []
    for row in rows:
        mood = str(row.get("mood_verdict") or "").strip().lower()
        personalised = str(row.get("personalised_template") or "").strip()
        guest = str(row.get("guest_template") or "").strip()
        if personalised:
            out.append(
                CoachTemplate(
                    slot="mood_voice_personalised",
                    template=personalised.replace("{first_name}", "{name}"),
                    conditions={"mood_verdict": mood} if mood else {},
                    weight=3,
                    tone="informative",
                )
            )
        if guest:
            out.append(
                CoachTemplate(
                    slot="mood_voice_guest",
                    template=guest,
                    conditions={"mood_verdict": mood} if mood else {},
                    weight=2,
                    tone="gentle",
                )
            )
    return out


@lru_cache(maxsize=1)
def load_coach_templates() -> list[CoachTemplate]:
    templates = _load_json_templates()
    try:
        from app.hlhp.evidence.loader import get_evidence_store

        store = get_evidence_store()
        wb_rows = store.composition.get("coach_voice_templates") or []
        templates = templates + _workbook_to_coach_templates(wb_rows)
    except FileNotFoundError:
        pass
    return templates
