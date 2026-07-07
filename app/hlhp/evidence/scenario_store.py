"""Runtime loader for the scenario library JSON snapshot."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "scenario_snapshot_v3_5.json"


class ScenarioStore:
    """In-memory view of SkinBB_HLHP_Scenario_Library."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.meta = snapshot.get("meta", {})
        self.version = str(self.meta.get("version", "3.5"))
        self.source = self.meta.get("source", "")
        self.bands: dict[str, list[dict[str, Any]]] = snapshot.get("bands", {})
        self.skins: list[str] = snapshot.get("skins", [])
        self.concerns: list[str] = snapshot.get("concerns", [])
        self.factors: list[str] = snapshot.get("factors", [])
        self.zones = snapshot.get("zones", {})
        self.zone_weather = snapshot.get("zone_weather", {})
        self.city_zone: dict[str, str] = snapshot.get("city_zone", {})
        self.master: dict[str, dict[str, Any]] = snapshot.get("master", {})
        self.compounds = snapshot.get("compounds", [])
        self.compound_cells: dict[str, dict[str, Any]] = snapshot.get("compound_cells", {})
        self.guest: dict[str, dict[str, Any]] = snapshot.get("guest", {})
        self.nuggets = snapshot.get("nuggets", [])
        self.nutrition = snapshot.get("nutrition", [])
        self.lifestyle = snapshot.get("lifestyle", [])
        self.gender_states = snapshot.get("gender_states", [])
        self.gender_rules: dict[str, dict[str, Any]] = snapshot.get("gender_rules", {})
        self.time_overlay: dict[str, dict[str, str]] = snapshot.get("time_overlay", {})

    @property
    def master_cell_count(self) -> int:
        return len(self.master)

    @property
    def guest_cell_count(self) -> int:
        return len(self.guest)

    @property
    def compound_cell_count(self) -> int:
        return len(self.compound_cells)

    @property
    def workbook_version(self) -> str:
        return self.source or self.version


@lru_cache(maxsize=1)
def get_scenario_store() -> ScenarioStore:
    if not _SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"Scenario snapshot missing at {_SNAPSHOT_PATH}. "
            "Run: python scripts/build_hlhp_scenario_library.py"
        )
    snapshot = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return ScenarioStore(snapshot)
