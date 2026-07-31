"""
Clear catalog product_analyses cache for one or more product ids.

Usage (from AI-Tools root):
  python scripts/clear_product_analysis_cache.py 6a0c4108c279308586234325
  python scripts/clear_product_analysis_cache.py --dry-run 6a0c4108c279308586234325

Uses MONGO_URI from .env (same as local and production).
Optional: --mongo-uri to override.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete product_analyses docs for product ids")
    parser.add_argument("product_ids", nargs="+", help="Mongo product ObjectId(s)")
    parser.add_argument("--dry-run", action="store_true", help="Show matches only")
    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="Override MONGO_URI",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Database name (default DB_NAME or skin_bb)",
    )
    args = parser.parse_args()

    uri = (args.mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "").strip().strip('"')
    if not uri:
        print("Missing MONGO_URI (or pass --mongo-uri)")
        return 1

    db_name = (args.db or os.getenv("DB_NAME") or "skin_bb").strip()
    source = "--mongo-uri" if args.mongo_uri else "MONGO_URI"
    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    try:
        db.command("ping")
    except ServerSelectionTimeoutError as e:
        print(f"Cannot reach Mongo ({source}): {e}")
        return 1

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

    print(f"\nDone via {source}/{db_name}. deleted_total={total} dry_run={args.dry_run}")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
