"""
Analyze alpha/beta/Greek-letter issues in ingre_inci and ingre_branded_ingredients.

Usage (from repo root):
  python app/ai_ingredient_intelligence/scripts/analyze_alpha_beta_prefixes.py
  python app/ai_ingredient_intelligence/scripts/analyze_alpha_beta_prefixes.py --export-csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin",
)
DB_NAME = os.getenv("DB_NAME", "skin_bb")

GREEK_RE = re.compile(r"[\u03b1-\u03c9\u0391-\u03a9]")
ESZETT_RE = re.compile(r"ß")
ALPHA_BETA_START = re.compile(r"^(alpha|beta)([\s\-]|$)", re.I)
ALPHA_BETA_GLUED = re.compile(r"^(alpha|beta)[a-z]", re.I)
DOUBLE_DASH = re.compile(r"--")
LONG_NAME = 200  # likely garbage import if inciName is this long

COLLECTIONS = [
    ("ingre_inci", "inciName", "inciName_normalized"),
    ("ingre_branded_ingredients", "ingredient_name", "ingredient_name_normalized"),
]

LEGITIMATE_PREFIXES = (
    "alpha-arbutin",
    "alpha arbutin",
    "alpha-tocopherol",
    "alpha tocopherol",
    "alpha-glucan",
    "alpha glucan",
    "alpha-hydroxy",
    "alpha hydroxy",
    "alpha-isomethyl",
    "alpha isomethyl",
    "alpha-terpineol",
    "alpha terpineol",
    "alpha-terpinene",
    "alpha terpinene",
    "alpha-amyrin",
    "alpha amyrin",
    "beta-glucan",
    "beta glucan",
    "beta-sitosterol",
    "beta sitosterol",
    "beta-carotene",
    "beta carotene",
    "beta-hydroxy",
    "beta hydroxy",
    "beta-caryophyllene",
    "beta caryophyllene",
    "beta-amyrin",
    "beta amyrin",
    "beta vulgaris",
    "beta-ionone",
    "beta ionone",
)

WRONG_ISOMERS = re.compile(r"beta[\s\-]?arbutin", re.I)


def seed_normalize(s: str) -> str:
    """Same logic as seed_db.normalize_text — strips Greek letters to ASCII."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


def classify_record(name: str) -> str:
    lower = name.lower().strip()
    if len(name) > LONG_NAME:
        return "garbage_long_name"
    if WRONG_ISOMERS.search(name):
        return "wrong_beta_arbutin"
    if GREEK_RE.search(name) or ESZETT_RE.search(name):
        return "greek_or_eszett"
    if ALPHA_BETA_START.search(name) or ALPHA_BETA_GLUED.search(name):
        if any(lower.startswith(p) for p in LEGITIMATE_PREFIXES):
            return "legitimate_alpha_beta_inci"
        if ALPHA_BETA_GLUED.search(name) and lower.startswith("betaine"):
            return "false_positive_betaine"
        return "alpha_beta_prefix_other"
    return "other"


def analyze_collection(db, coll_name: str, name_field: str, norm_field: str) -> dict:
    col = db[coll_name]
    total = col.count_documents({})

    category_counts: Counter[str] = Counter()
    category_samples: dict[str, list] = {k: [] for k in [
        "garbage_long_name",
        "wrong_beta_arbutin",
        "greek_or_eszett",
        "legitimate_alpha_beta_inci",
        "alpha_beta_prefix_other",
        "false_positive_betaine",
    ]}
    greek_corruption: list[dict] = []
    missing_normalized: list[str] = []
    prefix_form_counts: Counter[str] = Counter()

    for doc in col.find({}, {"_id": 1, name_field: 1, norm_field: 1}):
        name = (doc.get(name_field) or "").strip()
        if not name:
            continue

        cat = classify_record(name)
        category_counts[cat] += 1
        if cat in category_samples and len(category_samples[cat]) < 20:
            category_samples[cat].append(name)

        stored_norm = doc.get(norm_field)
        if stored_norm in (None, ""):
            if len(missing_normalized) < 15:
                missing_normalized.append(name)

        if GREEK_RE.search(name) or ESZETT_RE.search(name):
            computed = seed_normalize(name)
            if DOUBLE_DASH.search(computed) or (stored_norm and DOUBLE_DASH.search(stored_norm)):
                greek_corruption.append({
                    "name": name,
                    "stored_normalized": stored_norm or "",
                    "computed_normalized": computed,
                })

        m = re.match(r"^((?i:alpha|beta)[\s\-]?)", name)
        if m:
            prefix_form_counts[m.group(1).lower().rstrip("- ").strip() or m.group(1).lower()] += 1

    missing_norm_total = col.count_documents({
        "$or": [
            {norm_field: {"$exists": False}},
            {norm_field: None},
            {norm_field: ""},
        ],
        name_field: {"$exists": True, "$nin": [None, ""]},
    })

    alpha_beta_total = (
        category_counts["legitimate_alpha_beta_inci"]
        + category_counts["alpha_beta_prefix_other"]
        + category_counts["false_positive_betaine"]
    )

    return {
        "collection": coll_name,
        "name_field": name_field,
        "norm_field": norm_field,
        "total_documents": total,
        "missing_normalized_field": missing_norm_total,
        "alpha_beta_prefixed_names": alpha_beta_total,
        "category_counts": dict(category_counts),
        "prefix_form_counts": dict(prefix_form_counts),
        "samples": category_samples,
        "greek_letter_normalization_corruption": greek_corruption,
        "missing_normalized_samples": missing_normalized,
    }


def print_report(result: dict) -> None:
    coll = result["collection"]
    print(f"\n{'=' * 72}")
    print(f"Collection: {coll}")
    print(f"  Total documents: {result['total_documents']}")
    print(f"  Missing {result['norm_field']}: {result['missing_normalized_field']}")
    print(f"  Names starting with alpha/beta (excl. false positives): "
          f"{result['alpha_beta_prefixed_names']}")
    print(f"  Greek/eszett in name: {result['category_counts'].get('greek_or_eszett', 0)}")
    print(f"  Greek normalization corruption (double-dash): "
          f"{len(result['greek_letter_normalization_corruption'])}")
    print(f"  Wrong 'Beta Arbutin' entries: {result['category_counts'].get('wrong_beta_arbutin', 0)}")
    print(f"  Garbage long names (> {LONG_NAME} chars): "
          f"{result['category_counts'].get('garbage_long_name', 0)}")

    print("\n  Category breakdown:")
    for cat, count in sorted(result["category_counts"].items(), key=lambda x: -x[1]):
        if count:
            print(f"    {cat}: {count}")

    if result["prefix_form_counts"]:
        print(f"\n  Prefix forms: {result['prefix_form_counts']}")

    for label in [
        "wrong_beta_arbutin",
        "greek_or_eszett",
        "alpha_beta_prefix_other",
        "garbage_long_name",
        "legitimate_alpha_beta_inci",
    ]:
        samples = result["samples"].get(label, [])
        if samples:
            print(f"\n  Samples — {label}:")
            for s in samples[:10]:
                safe = s.encode("utf-8", errors="replace").decode("utf-8")
                print(f"    - {safe[:120]}{'...' if len(s) > 120 else ''}")

    if result["greek_letter_normalization_corruption"]:
        print("\n  Greek/eszett normalization corruption:")
        for row in result["greek_letter_normalization_corruption"][:10]:
            print(f"    name: {row['name'][:90]}")
            print(f"      stored: {row['stored_normalized'][:90] or '(empty)'}")
            print(f"      computed: {row['computed_normalized'][:90]}")
            print()


def write_csv(results: list[dict], path: Path) -> None:
    rows = []
    for result in results:
        coll = result["collection"]
        name_field = result["name_field"]
        for cat, names in result["samples"].items():
            for name in names:
                rows.append({
                    "collection": coll,
                    "name_field": name_field,
                    "category": cat,
                    "name": name,
                    "stored_normalized": "",
                    "computed_normalized": "",
                })
        for row in result["greek_letter_normalization_corruption"]:
            rows.append({
                "collection": coll,
                "name_field": name_field,
                "category": "greek_normalization_corruption",
                "name": row["name"],
                "stored_normalized": row["stored_normalized"],
                "computed_normalized": row["computed_normalized"],
            })

    fieldnames = [
        "collection",
        "name_field",
        "category",
        "name",
        "stored_normalized",
        "computed_normalized",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Analyze alpha/beta prefix data quality")
    parser.add_argument("--export-csv", action="store_true", help="Write samples to CSV")
    args = parser.parse_args()

    print(f"Connecting to {DB_NAME} ...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
    db = client[DB_NAME]
    client.admin.command("ping")
    print("Connected.")

    results = []
    for coll_name, name_field, norm_field in COLLECTIONS:
        print(f"\nScanning {coll_name} ...")
        results.append(analyze_collection(db, coll_name, name_field, norm_field))

    for result in results:
        print_report(result)

    out_dir = Path(__file__).parent
    json_path = out_dir / "alpha_beta_prefix_analysis.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root_cause_notes": [
            "seed_db.normalize_text() strips Greek α/β and ß via ASCII encode, leaving double hyphens "
            "(e.g. '18-β-Glycyrrhetinic' -> '18--glycyrrhetinic').",
            "Many branded ingredients lack ingredient_name_normalized (legacy/backfill gap).",
            "Literal 'alpha'/'beta' prefixes are mostly legitimate INCI isomers or supplier trade names.",
            "Wrong 'Beta Arbutin' entries should be Alpha Arbutin.",
            "Some ingre_inci rows have entire product descriptions in inciName (bad import).",
        ],
        "results": results,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nJSON report: {json_path}")

    if args.export_csv:
        csv_path = out_dir / "alpha_beta_prefix_samples.csv"
        write_csv(results, csv_path)
        print(f"CSV samples: {csv_path}")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    for r in results:
        print(
            f"{r['collection']}: "
            f"{r['alpha_beta_prefixed_names']} alpha/beta names, "
            f"{r['category_counts'].get('greek_or_eszett', 0)} Greek/eszett, "
            f"{len(r['greek_letter_normalization_corruption'])} norm corruption, "
            f"{r['missing_normalized_field']} missing normalized field"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
