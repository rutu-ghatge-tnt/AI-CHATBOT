"""
Clear catalog product_analyses cache for one or more product ids.

Usage (from AI-Tools root):
  python scripts/clear_product_analysis_cache.py 6a0c4108c279308586234325
  python scripts/clear_product_analysis_cache.py --production 6a0c4108c279308586234325
  python scripts/clear_product_analysis_cache.py --dry-run 6a0c4108c279308586234325

Uses MONGO_URI by default; --production uses PRODUCTION_MONGO_URI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete product_analyses docs for product ids")
    parser.add_argument("product_ids", nargs="+", help="Mongo product ObjectId(s)")
    parser.add_argument("--production", action="store_true", help="Use PRODUCTION_MONGO_URI")
    parser.add_argument("--dry-run", action="store_true", help="Show matches only")
    parser.add_argument(
        "--db",
        default=None,
        help="Database name (default DB_NAME or skin_bb)",
    )
    args = parser.parse_args()

    import os

    if args.production:
        uri = (os.getenv("PRODUCTION_MONGO_URI") or "").strip().strip('"')
        label = "PRODUCTION_MONGO_URI"
    else:
        uri = (os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "").strip()
        label = "MONGO_URI"
    if not uri:
        print(f"Missing {label}")
        return 1

    db_name = (args.db or os.getenv("DB_NAME") or "skin_bb").strip()
    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    db.command("ping")
    coll = db["product_analyses"]

    total = 0
    for raw in args.product_ids:
        pid = raw.strip()
        oid = ObjectId(pid) if ObjectId.is_valid(pid) else None
        filt = {"$or": [{"_id": oid}, {"productId": oid}]} if oid else {"productId": pid}
        docs = list(coll.find(filt, {"productId": 1, "productName": 1, "updatedAt": 1, "ingredients": 1}))
        print(f"\nproduct {pid}: {len(docs)} analysis doc(s)")
        for d in docs:
            ings = d.get("ingredients") or []
            print(
                f"  _id={d.get('_id')} productId={d.get('productId')} "
                f"updatedAt={d.get('updatedAt')} ings={len(ings)} "
                f"has_BHT={'BHT' in str(ings) or 'BHT' in str(d)}"
            )
        if args.dry_run:
            continue
        res = coll.delete_many(filt)
        total += res.deleted_count
        print(f"  deleted={res.deleted_count}")

    print(f"\nDone via {label}/{db_name}. deleted_total={total} dry_run={args.dry_run}")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
