"""
Strip supplier tag (Alfa) from ingre_branded_ingredients.ingredient_name.

The Alfa Chemistry import (Dec 2025) incorrectly embedded "(Alfa)" in names:
  - "Tocopherol (Alfa)"  -> "Tocopherol"
  - "(Alfa) Aqua"        -> "Aqua"
  - "(Alfa) alpha-Arbutin" -> "alpha-Arbutin"

Usage (from repo root):
  python app/ai_ingredient_intelligence/scripts/cleanup_alfa_supplier_prefix.py
  python app/ai_ingredient_intelligence/scripts/cleanup_alfa_supplier_prefix.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")

MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://skinbb_owner:SkinBB%4054321@93.127.194.42:27017/skin_bb?authSource=admin",
)
DB_NAME = os.getenv("DB_NAME", "skin_bb")

ALFA_TAG_RE = re.compile(r"\(\s*alfa\s*\)", re.IGNORECASE)
COLLECTION = "ingre_branded_ingredients"


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


def clean_alfa_tag(name: str) -> str:
    """Remove (Alfa) supplier tag and tidy whitespace."""
    cleaned = ALFA_TAG_RE.sub("", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Remove (Alfa) supplier tags from branded ingredient names")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to MongoDB (default is dry-run only)",
    )
    parser.add_argument(
        "--supplier-only",
        action="store_true",
        help="Only fix rows from supplier 'Alfa Chemistry' (default: any row with (Alfa) in name)",
    )
    args = parser.parse_args()

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=20000)
    db = client[DB_NAME]
    col = db[COLLECTION]

    query: dict = {"ingredient_name": ALFA_TAG_RE}
    if args.supplier_only:
        sup = db["ingre_suppliers"].find_one({"supplierName": "Alfa Chemistry"}, {"_id": 1})
        if not sup:
            print("Supplier 'Alfa Chemistry' not found.")
            return 1
        query["supplier_id"] = sup["_id"]

    docs = list(
        col.find(
            query,
            {"ingredient_name": 1, "ingredient_name_normalized": 1, "supplier_id": 1},
        )
    )
    print(f"Found {len(docs)} documents with (Alfa) in ingredient_name")
    if not docs:
        return 0

    # Build normalized-name index for collision detection
    existing_by_norm: dict[str, list[dict]] = {}
    for doc in col.find({}, {"_id": 1, "ingredient_name": 1, "ingredient_name_normalized": 1, "supplier_id": 1}):
        name = (doc.get("ingredient_name") or "").strip()
        norm = doc.get("ingredient_name_normalized") or normalize_text(name)
        existing_by_norm.setdefault(norm, []).append(doc)

    updates: list[dict] = []
    skipped: list[dict] = []
    unchanged: list[dict] = []

    for doc in docs:
        old_name = (doc.get("ingredient_name") or "").strip()
        new_name = clean_alfa_tag(old_name)
        if not new_name:
            skipped.append({"_id": str(doc["_id"]), "reason": "empty after strip", "old_name": old_name})
            continue
        if new_name == old_name:
            unchanged.append({"_id": str(doc["_id"]), "old_name": old_name})
            continue

        new_norm = normalize_text(new_name)
        doc_id = doc["_id"]
        others = [d for d in existing_by_norm.get(new_norm, []) if d["_id"] != doc_id]
        if others:
            skipped.append({
                "_id": str(doc_id),
                "reason": "collision",
                "old_name": old_name,
                "new_name": new_name,
                "existing_ids": [str(d["_id"]) for d in others[:3]],
                "existing_names": [(d.get("ingredient_name") or "") for d in others[:3]],
            })
            continue

        updates.append({
            "_id": doc_id,
            "old_name": old_name,
            "new_name": new_name,
            "old_normalized": doc.get("ingredient_name_normalized") or "",
            "new_normalized": new_norm,
        })

    print(f"\n  Will update: {len(updates)}")
    print(f"  Skipped:     {len(skipped)}")
    print(f"  Unchanged:   {len(unchanged)}")

    print("\nSample updates:")
    for row in updates[:15]:
        print(f"  {row['old_name']!r}")
        print(f"    -> {row['new_name']!r}")
    if len(updates) > 15:
        print(f"  ... and {len(updates) - 15} more")

    if skipped:
        print("\nSkipped:")
        for row in skipped[:10]:
            print(f"  {row['_id']}: {row.get('reason')} — {row.get('old_name', '')!r}")
            if row.get("existing_names"):
                print(f"    conflicts with: {row['existing_names']}")

    report_path = Path(__file__).parent / "cleanup_alfa_supplier_prefix_report.json"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": not args.apply,
        "query": {k: str(v) if isinstance(v, ObjectId) else v for k, v in query.items()},
        "update_count": len(updates),
        "skipped_count": len(skipped),
        "updates": [
            {**{k: (str(v) if k == "_id" else v) for k, v in row.items()}}
            for row in updates
        ],
        "skipped": skipped,
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nReport: {report_path}")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write changes.")
        return 0

    modified = 0
    for row in updates:
        result = col.update_one(
            {"_id": row["_id"]},
            {
                "$set": {
                    "ingredient_name": row["new_name"],
                    "ingredient_name_normalized": row["new_normalized"],
                }
            },
        )
        if result.modified_count:
            modified += 1

    print(f"\nApplied {modified} updates.")
    remaining = col.count_documents({"ingredient_name": ALFA_TAG_RE})
    print(f"Remaining rows with (Alfa) in name: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
