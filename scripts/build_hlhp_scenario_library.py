#!/usr/bin/env python3
"""Export SkinBB_HLHP_Scenario_Library workbook to a versioned JSON snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hlhp.evidence.scenario_workbook import DEFAULT_XLSX, build_scenario_snapshot

OUT_PATH = ROOT / "app" / "hlhp" / "data" / "scenario_snapshot_v3_6.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HLHP scenario library JSON snapshot")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    if not args.xlsx.exists():
        print(f"Workbook not found: {args.xlsx}", file=sys.stderr)
        return 1

    snapshot = build_scenario_snapshot(args.xlsx)
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(payload, encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  master cells   : {snapshot['meta']['master_cell_count']}")
    print(f"  compound cells : {snapshot['meta']['compound_cell_count']}")
    print(f"  guest cells    : {snapshot['meta'].get('guest_cell_count', 0)}")
    print(f"  gender states  : {snapshot['meta'].get('gender_state_count', 0)}")
    print(f"  gender rules   : {snapshot['meta'].get('gender_rule_count', 0)}")
    print(f"  time overlays  : {snapshot['meta'].get('time_overlay_count', 0)}")
    print(f"  cities mapped  : {len(snapshot['city_zone'])}")
    print()
    print("To activate this snapshot in the API, run:")
    print(f"  python scripts/update_hlhp_library.py --xlsx {args.xlsx}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
