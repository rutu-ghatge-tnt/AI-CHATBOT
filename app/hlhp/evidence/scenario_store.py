"""Runtime loader for the scenario library JSON snapshot."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.hlhp.config import hl_settings

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_DEFAULT_SNAPSHOT = _DATA_DIR / "scenario_snapshot_v3_6.json"
_FALLBACK_SNAPSHOT = _DATA_DIR / "scenario_snapshot_v3_5.json"
_ACTIVE_POINTER = _DATA_DIR / "scenario_snapshot_active.json"


def resolve_snapshot_path() -> Path:
    """
    Resolve the active scenario library snapshot.

    Priority: HL_SCENARIO_SNAPSHOT env → active pointer file → default v3.6 path
    → v3.5 fallback.
    """
    if hl_settings.HL_SCENARIO_SNAPSHOT:
        return Path(hl_settings.HL_SCENARIO_SNAPSHOT)
    if _ACTIVE_POINTER.exists():
        try:
            meta = json.loads(_ACTIVE_POINTER.read_text(encoding="utf-8"))
            rel = meta.get("path") or meta.get("snapshot")
            if rel:
                p = Path(rel)
                if not p.is_absolute():
                    p = _DATA_DIR / p
                if p.exists():
                    return p
        except (json.JSONDecodeError, OSError):
            pass
    if _DEFAULT_SNAPSHOT.exists():
        return _DEFAULT_SNAPSHOT
    return _FALLBACK_SNAPSHOT


def _slug(s: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")


def _normalize_guest(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Accept v3.5 ``guest`` or v3.6 ``guest_mode`` + ``guest_compounds``."""
    guest = dict(snapshot.get("guest") or {})
    if guest:
        return guest
    for key, cell in (snapshot.get("guest_mode") or {}).items():
        if isinstance(cell, dict):
            guest[f"single|{key}|none"] = cell
            guest[str(key)] = cell
    for cell in snapshot.get("guest_compounds") or []:
        if not isinstance(cell, dict):
            continue
        name = str(cell.get("factor") or cell.get("scenario") or "").strip()
        skin = str(cell.get("skin") or "Normal").strip()
        if name:
            guest[f"compound|{_slug(name)}|{_slug(skin)}|none"] = cell
    return guest


class ScenarioStore:
    """In-memory view of SkinBB_HLHP_Scenario_Library."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.meta = snapshot.get("meta", {})
        self.version = str(self.meta.get("version", "3.6"))
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
        self.guest: dict[str, dict[str, Any]] = _normalize_guest(snapshot)
        self.nuggets = snapshot.get("nuggets", [])
        self.nutrition = snapshot.get("nutrition", [])
        self.lifestyle = snapshot.get("lifestyle", [])
        self.gender_states = snapshot.get("gender_states", [])
        self.gender_rules: dict[str, dict[str, Any]] = snapshot.get("gender_rules", {})
        self.age_bands = snapshot.get("age_bands", [])
        self.age_rules: dict[str, dict[str, Any]] = snapshot.get("age_rules", {})
        self.routine_rules: list[dict[str, Any]] = list(snapshot.get("routine_rules") or [])
        self.time_overlay: dict[str, dict[str, str]] = snapshot.get("time_overlay", {})
        self.skin_band_penalty: dict[str, Any] = snapshot.get("skin_band_penalty", {})

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
    path = resolve_snapshot_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Scenario snapshot missing at {path}. "
            "Run: python scripts/update_hlhp_library.py --xlsx <workbook>"
        )
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioStore(snapshot)


def reload_scenario_store() -> ScenarioStore:
    """Clear cached store after a library update (call from update script or admin)."""
    get_scenario_store.cache_clear()
    return get_scenario_store()


def write_active_pointer(snapshot_path: Path, *, version: str = "") -> None:
    """Record which snapshot file the API should load."""
    rel = snapshot_path.name if snapshot_path.parent == _DATA_DIR else str(snapshot_path)
    payload = {
        "path": rel,
        "version": version,
        "absolute": str(snapshot_path.resolve()),
    }
    _ACTIVE_POINTER.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.environ["HL_SCENARIO_SNAPSHOT"] = str(snapshot_path.resolve())
