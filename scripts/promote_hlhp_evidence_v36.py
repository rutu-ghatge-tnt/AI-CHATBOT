#!/usr/bin/env python3
"""Promote Suite Release evidence v3.6 into the production scenario snapshot.

Merges runtime fields the v3.6 export omits (bands, time_overlay, zone_weather)
from the prior v3.5 snapshot so the Python engine keeps working, and normalizes
guest_mode / guest_compounds into the engine's ``guest`` key shape.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "hlhp" / "data"
SUITE_EVIDENCE = (
    ROOT
    / "app"
    / "hlhp"
    / "HLHP Suite Release"
    / "6 - Evidence Library"
    / "evidence"
    / "hlhp-evidence.json"
)
V35 = DATA / "scenario_snapshot_v3_5.json"
OUT = DATA / "scenario_snapshot_v3_6.json"
ROUTINE_OUT = DATA / "routine_rules_v1.json"
ACTIVE = DATA / "scenario_snapshot_active.json"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")


def build_guest_map(ref: dict) -> dict:
    """Engine expects single|factor|band|skin|none and compound|scenario|skin|none."""
    guest: dict = {}
    for key, cell in (ref.get("guest_mode") or {}).items():
        if not isinstance(cell, dict):
            continue
        guest[f"single|{key}|none"] = cell
        # Also keep the raw v3.6 key for defensive lookups.
        guest[key] = cell
    for cell in ref.get("guest_compounds") or []:
        if not isinstance(cell, dict):
            continue
        name = str(cell.get("factor") or cell.get("scenario") or "").strip()
        skin = str(cell.get("skin") or "Normal").strip()
        if not name:
            continue
        guest[f"compound|{slug(name)}|{slug(skin)}|none"] = cell
    return guest


def main() -> int:
    if not SUITE_EVIDENCE.exists():
        print(f"Missing Suite Release evidence: {SUITE_EVIDENCE}", file=sys.stderr)
        return 1
    if not V35.exists():
        print(f"Missing v3.5 snapshot for band/time merge: {V35}", file=sys.stderr)
        return 1

    ref = json.loads(SUITE_EVIDENCE.read_text(encoding="utf-8"))
    prior = json.loads(V35.read_text(encoding="utf-8"))

    bands = ref.get("bands") or prior.get("bands") or {}
    if not bands:
        print("ERROR: no band tables in v3.6 or v3.5", file=sys.stderr)
        return 1

    guest = build_guest_map(ref)
    if not guest and prior.get("guest"):
        guest = prior["guest"]

    time_overlay = ref.get("time_overlay") or prior.get("time_overlay") or {}

    snapshot = {
        "meta": {
            **(ref.get("meta") or {}),
            "version": str((ref.get("meta") or {}).get("version") or "3.6"),
            "promoted_from": str(SUITE_EVIDENCE.as_posix()),
            "runtime_merge": {
                "bands": "v3.5" if not (ref.get("bands") or {}) else "v3.6",
                "time_overlay": "v3.5" if not ref.get("time_overlay") else "v3.6",
                "zone_weather": "v3.5",
                "guest_normalized": True,
            },
            "master_cell_count": len(ref.get("master") or {}),
            "compound_cell_count": len(ref.get("compound_cells") or {}),
            "guest_cell_count": len(guest),
            "gender_state_count": len(ref.get("gender_states") or []),
            "gender_rule_count": len(ref.get("gender_rules") or {}),
            "age_rule_count": len(ref.get("age_rules") or {}),
            "routine_rule_count": len(ref.get("routine_rules") or []),
            "time_overlay_count": len(time_overlay),
        },
        "bands": bands,
        "skins": ref.get("skins") or prior.get("skins") or [],
        "concerns": ref.get("concerns") or prior.get("concerns") or [],
        "factors": prior.get("factors")
        or list((bands or {}).keys())
        or ["Temperature", "UV", "Humidity", "AQI"],
        "zones": ref.get("zones") or prior.get("zones") or {},
        "zone_weather": prior.get("zone_weather") or {},
        "city_zone": ref.get("city_zone") or prior.get("city_zone") or {},
        "master": ref.get("master") or {},
        "compounds": ref.get("compounds") or [],
        "compound_cells": ref.get("compound_cells") or {},
        "guest": guest,
        "guest_mode": ref.get("guest_mode") or {},
        "guest_compounds": ref.get("guest_compounds") or [],
        "nuggets": ref.get("nuggets") or [],
        "nutrition": ref.get("nutrition") or [],
        "lifestyle": ref.get("lifestyle") or [],
        "gender_states": ref.get("gender_states") or [],
        "gender_rules": ref.get("gender_rules") or {},
        "age_bands": ref.get("age_bands") or [],
        "age_rules": ref.get("age_rules") or {},
        "routine_rules": ref.get("routine_rules") or [],
        "time_overlay": time_overlay,
        "time_overlay_raw": ref.get("time_overlay_raw"),
        "skin_band_penalty": prior.get("skin_band_penalty") or {},
    }

    OUT.write_text(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    rules = snapshot["routine_rules"]
    ROUTINE_OUT.write_text(
        json.dumps(
            {
                "version": "3.6",
                "source": "hlhp-evidence.json routine_rules (v3.6)",
                "rules": rules,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ACTIVE.write_text(
        json.dumps(
            {
                "path": OUT.name,
                "version": snapshot["meta"]["version"],
                "absolute": str(OUT.resolve()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {OUT}")
    print(f"  version          : {snapshot['meta']['version']}")
    print(f"  master           : {snapshot['meta']['master_cell_count']}")
    print(f"  compounds        : {snapshot['meta']['compound_cell_count']}")
    print(f"  guest (normalized): {snapshot['meta']['guest_cell_count']}")
    print(f"  age_rules        : {snapshot['meta']['age_rule_count']}")
    print(f"  routine_rules    : {snapshot['meta']['routine_rule_count']}")
    print(f"  time_overlay     : {snapshot['meta']['time_overlay_count']}")
    print(f"Wrote {ROUTINE_OUT}")
    print(f"Wrote {ACTIVE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
