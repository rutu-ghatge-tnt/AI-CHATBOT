from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.hlhp.evidence.index import EvidenceIndex, build_inverted_index
from app.hlhp.evidence.models import EvidenceFinding, ScienceNugget

_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "evidence_snapshot_v1.json"


class EvidenceStore:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.version = int(snapshot.get("version", 1))
        self.generated_at = snapshot.get("generated_at", "")
        self.readme = snapshot.get("readme", {})
        self.book_inventory = snapshot.get("book_inventory", [])
        self.findings = [EvidenceFinding.from_dict(row) for row in snapshot.get("findings", [])]
        self.findings_by_id = {f.id: f for f in self.findings}
        self.nuggets = [ScienceNugget.from_dict(row) for row in snapshot.get("science_nuggets", [])]
        raw_index = snapshot.get("inverted_index")
        if raw_index:
            self.index = EvidenceIndex(raw_index, self.findings_by_id)
        else:
            self.index = EvidenceIndex(build_inverted_index(snapshot.get("findings", [])), self.findings_by_id)
        self.glossary = snapshot.get("glossary", [])
        self.gaps_conflicts = snapshot.get("gaps_conflicts", [])
        self.coverage_matrix = snapshot.get("coverage_matrix", {})
        self.build_report = snapshot.get("build_report", {})
        self._glossary_by_term = {
            (e.get("term") or "").lower(): e for e in self.glossary if e.get("term")
        }


@lru_cache(maxsize=1)
def get_evidence_store() -> EvidenceStore:
    if not _SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"Evidence snapshot missing at {_SNAPSHOT_PATH}. "
            "Run: python scripts/build_hlhp_evidence.py"
        )
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return EvidenceStore(snapshot)
