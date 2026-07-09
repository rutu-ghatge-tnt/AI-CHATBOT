"""Runtime loader for Layer 2 composition content (UI deep-dives, guides, forecasts)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "composition_snapshot.json"


class CompositionStore:
    """In-memory view of HLHP composition tables (concern pages, guides, etc.)."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.version = str(snapshot.get("version", "3.5"))
        self.source = str(snapshot.get("source", ""))
        self.generated_at = str(snapshot.get("generated_at", ""))
        self.composition: dict[str, Any] = snapshot.get("composition", {})
        self.workbook_version = self.source or self.version


@lru_cache(maxsize=1)
def get_composition_store() -> CompositionStore:
    if not _SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"Composition snapshot missing at {_SNAPSHOT_PATH}. "
            "Rebuild from scenario library tooling or restore composition_snapshot.json."
        )
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return CompositionStore(snapshot)
