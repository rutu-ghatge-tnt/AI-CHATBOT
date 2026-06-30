#!/usr/bin/env python3
"""Export SkinBB_HLHP_Scenario_Library_v3_4.xlsx to a versioned JSON snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hlhp.evidence.scenario_workbook import DEFAULT_XLSX, build_scenario_snapshot

OUT_PATH = ROOT / "app" / "hlhp" / "data" / "scenario_snapshot_v3_4.json"
UI_OUT_PATH = ROOT / "app" / "hlhp" / "data" / "hlhp-ui" / "public" / "hlhp-evidence.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HLHP scenario library JSON snapshot")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--ui-out", type=Path, default=UI_OUT_PATH, help="Also refresh hlhp-ui public JSON")
    parser.add_argument("--skip-ui", action="store_true")
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
    print(f"  cities mapped  : {len(snapshot['city_zone'])}")

    if not args.skip_ui:
        args.ui_out.parent.mkdir(parents=True, exist_ok=True)
        args.ui_out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.ui_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
