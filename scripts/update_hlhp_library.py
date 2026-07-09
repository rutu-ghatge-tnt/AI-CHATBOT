#!/usr/bin/env python3
"""
Update HLHP scenario library from a new workbook export.

Usage:
  python scripts/update_hlhp_library.py --xlsx app/hlhp/data/SkinBB_HLHP_Scenario_Library_v4.0.xlsx

Writes a versioned JSON snapshot, updates the active pointer, and refreshes
optional skin_band_penalty.json when the snapshot includes that table.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hlhp.data import v4_scoring_data
from app.hlhp.evidence.scenario_store import reload_scenario_store, write_active_pointer
from app.hlhp.evidence.scenario_workbook import DEFAULT_XLSX, build_scenario_snapshot

DATA_DIR = ROOT / "app" / "hlhp" / "data"
DEFAULT_OUT = DATA_DIR / "scenario_snapshot_v3_5.json"
PENALTY_JSON = DATA_DIR / "skin_band_penalty.json"


def _version_slug(xlsx: Path, meta: dict) -> str:
    ver = str(meta.get("version") or "")
    if ver:
        return ver.replace(".", "_")
    m = re.search(r"v([\d_.]+)", xlsx.name, re.I)
    if m:
        return m.group(1).replace(".", "_")
    return "custom"


def main() -> int:
    parser = argparse.ArgumentParser(description="Update HLHP scenario library from workbook")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="Path to .xlsx library")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: versioned file under app/hlhp/data/)",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        default=True,
        help="Point runtime at the new snapshot (default: true)",
    )
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="Build snapshot only; do not switch active pointer",
    )
    args = parser.parse_args()

    if not args.xlsx.exists():
        print(f"Workbook not found: {args.xlsx}", file=sys.stderr)
        return 1

    snapshot = build_scenario_snapshot(args.xlsx)
    meta = snapshot.get("meta") or {}
    version_slug = _version_slug(args.xlsx, meta)
    out_path = args.out or (DATA_DIR / f"scenario_snapshot_v{version_slug}.json")

    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"  version          : {meta.get('version', '?')}")
    print(f"  master cells     : {meta.get('master_cell_count', 0)}")
    print(f"  compound cells   : {meta.get('compound_cell_count', 0)}")
    print(f"  cities mapped    : {len(snapshot.get('city_zone') or {})}")

    penalty = snapshot.get("skin_band_penalty")
    if isinstance(penalty, dict) and penalty:
        PENALTY_JSON.write_text(json.dumps(penalty, indent=2), encoding="utf-8")
        v4_scoring_data.reload_skin_band_penalty()
        print(f"  skin_band_penalty: updated {PENALTY_JSON.name}")
    else:
        print("  skin_band_penalty: unchanged (not in workbook snapshot)")

    if args.activate and not args.no_activate:
        write_active_pointer(out_path, version=str(meta.get("version", "")))
        store = reload_scenario_store()
        print(f"  active snapshot  : {out_path.name} (v{store.version})")
    else:
        print("  active snapshot  : not changed (use --activate to switch)")

    # Keep legacy default filename in sync when version matches
    if out_path != DEFAULT_OUT and "3_5" in out_path.name:
        shutil.copy2(out_path, DEFAULT_OUT)
        print(f"  synced legacy    : {DEFAULT_OUT.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
