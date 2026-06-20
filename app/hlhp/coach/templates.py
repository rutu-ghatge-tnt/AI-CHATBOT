from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.hlhp.coach.models import CoachTemplate

_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "data" / "coach_templates_v1.json"


@lru_cache(maxsize=1)
def load_coach_templates() -> list[CoachTemplate]:
    if not _TEMPLATES_PATH.exists():
        return []
    raw = json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [CoachTemplate.model_validate(row) for row in raw]
