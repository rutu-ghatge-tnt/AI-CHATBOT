#!/usr/bin/env python3
"""Export HLHP_Evidence_Base.xlsx to a versioned JSON snapshot for runtime matching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hlhp.evidence.workbook import build_snapshot, sync_workbook_coverage_matrix, sync_workbook_user_filters

XLSX_PATH = ROOT / "app" / "hlhp" / "docs" / "HLHP_Evidence_Base.xlsx"
OUT_PATH = ROOT / "app" / "hlhp" / "data" / "evidence_snapshot_v1.json"
REPORT_PATH = ROOT / "app" / "hlhp" / "data" / "evidence_build_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HLHP evidence JSON snapshot")
    parser.add_argument("--xlsx", type=Path, default=XLSX_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--strict", action="store_true", help="Fail on build warnings")
    args = parser.parse_args()

    snapshot = build_snapshot(args.xlsx)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    filter_updates = 0
    try:
        sync_workbook_coverage_matrix(args.xlsx, snapshot["coverage_matrix"]["grids"])
        filter_updates = sync_workbook_user_filters(args.xlsx, snapshot["findings"])
    except OSError as exc:
        print(f"Note: could not update xlsx (close file if open): {exc}")

    report = {
        "generated_at": snapshot["generated_at"],
        "source_workbook": snapshot["source_workbook"],
        "sheets_exported": [
            "README",
            "Book Inventory",
            "UV",
            "Temperature",
            "Humidity",
            "Pollution",
            "Nutritional Status",
            "Lifestyle",
            "Science Nuggets",
            "Glossary",
            "Gaps & Conflicts",
            "Coverage_Matrix",
        ],
        "counts": {
            "findings": snapshot["finding_count"],
            "science_nuggets": snapshot["nugget_count"],
            "book_inventory": len(snapshot.get("book_inventory", [])),
            "glossary": len(snapshot.get("glossary", [])),
            "gaps_conflicts": len(snapshot.get("gaps_conflicts", [])),
            "coverage_grids": len(snapshot.get("coverage_matrix", {}).get("grids", [])),
        },
        "build_autofixes": snapshot.get("build_autofixes", []),
        "build_warnings": snapshot.get("build_warnings", []),
        "build_report": snapshot.get("build_report", {}),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {snapshot['finding_count']} findings to {args.out}")
    print(f"Build report -> {args.report}")
    br = snapshot.get("build_report", {})
    print(
        f"Sheets: README, Book Inventory ({report['counts']['book_inventory']}), "
        f"6 factors ({snapshot['finding_count']}), Science Nuggets ({report['counts']['science_nuggets']}), "
        f"Glossary ({report['counts']['glossary']}), Gaps ({report['counts']['gaps_conflicts']}), "
        f"Coverage ({report['counts']['coverage_grids']} grids)"
    )
    if br:
        cov = br.get("coverage_report", {})
        print(
            f"Validation: voice={len(br.get('voice_violations', []))}, "
            f"citations={len(br.get('citation_issues', []))}, "
            f"coverage_gaps={cov.get('true_gap_count', 0)}"
        )
    if filter_updates:
        print(f"Workbook user-filter cells updated: {filter_updates}")
    if snapshot.get("build_autofixes"):
        print(f"Auto-fixes ({len(snapshot['build_autofixes'])}):")
        for fix in snapshot["build_autofixes"][:5]:
            print(f"  + {fix}")
    if snapshot["build_warnings"]:
        print(f"Warnings ({len(snapshot['build_warnings'])}):")
        for w in snapshot["build_warnings"][:10]:
            print(f"  - {w}")
        if len(snapshot["build_warnings"]) > 10:
            print(f"  ... and {len(snapshot['build_warnings']) - 10} more")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
