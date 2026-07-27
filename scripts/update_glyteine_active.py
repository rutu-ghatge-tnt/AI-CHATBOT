"""Set Glyteine / Gamma-Glutamylcysteine category to Active.

Default: MONGO_URI / MONGODB_URI (dev).
Production: --production uses PRODUCTION_MONGO_URI / PROD_MONGO_URI.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
import os

load_dotenv()

# Known ids on the shared/dev host (93.x). Prod is resolved by name first.
DEV_BRANDED_ID = ObjectId("6a4f741ec08fcb0e5d8d33b9")
DEV_INCI_ID = ObjectId("6a4cf3bf0aa9e63c2aeb874d")


def _redact_uri(uri: str) -> str:
    try:
        p = urlparse(uri)
        host = p.hostname or "?"
        port = f":{p.port}" if p.port else ""
        db = (p.path or "/").lstrip("/") or "?"
        return f"{p.scheme}://{p.username or '?'}:***@{host}{port}/{db}"
    except Exception:
        return "***"


def _resolve_uri(*, production: bool, mongo_uri: str | None) -> str:
    if mongo_uri and mongo_uri.strip():
        return mongo_uri.strip()
    if production:
        uri = (os.getenv("PRODUCTION_MONGO_URI") or os.getenv("PROD_MONGO_URI") or "").strip()
        if not uri:
            raise SystemExit(
                "Production mode requires PRODUCTION_MONGO_URI (or PROD_MONGO_URI) in .env, "
                "or pass --mongo-uri"
            )
        return uri
    uri = (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
    if not uri:
        raise SystemExit("MONGO_URI / MONGODB_URI is required")
    return uri


def _find_branded(db):
    doc = db.ingre_branded_ingredients.find_one(
        {
            "$or": [
                {"ingredient_name": {"$regex": "^Glyteine$", "$options": "i"}},
                {"original_inci_name": {"$regex": "^Gamma-Glutamylcysteine$", "$options": "i"}},
            ]
        },
        {
            "ingredient_name": 1,
            "original_inci_name": 1,
            "category_decided": 1,
            "functional_category_ids": 1,
            "chemical_class_ids": 1,
            "description": 1,
            "enhanced_description": 1,
        },
    )
    if doc:
        return doc
    return db.ingre_branded_ingredients.find_one(
        {"_id": DEV_BRANDED_ID},
        {
            "ingredient_name": 1,
            "original_inci_name": 1,
            "category_decided": 1,
            "functional_category_ids": 1,
            "chemical_class_ids": 1,
            "description": 1,
            "enhanced_description": 1,
        },
    )


def _find_inci(db):
    doc = db.ingre_inci.find_one(
        {
            "$or": [
                {"inciName": {"$regex": "^Gamma-Glutamylcysteine$", "$options": "i"}},
                {"inciName_normalized": "gamma-glutamylcysteine"},
            ]
        },
        {"inciName": 1, "category": 1, "functionality": 1, "description": 1},
    )
    if doc:
        return doc
    return db.ingre_inci.find_one(
        {"_id": DEV_INCI_ID},
        {"inciName": 1, "category": 1, "functionality": 1, "description": 1},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark Glyteine as Active in branded + INCI")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use PRODUCTION_MONGO_URI (prod host 10.0.128.233)",
    )
    parser.add_argument(
        "--mongo-uri",
        default=None,
        help="Explicit Mongo URI (e.g. SSH tunnel mongodb://...@127.0.0.1:27018/skin_bb)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Find docs and print; do not write",
    )
    args = parser.parse_args()

    uri = _resolve_uri(production=args.production, mongo_uri=args.mongo_uri)
    print(f"target={'PRODUCTION' if args.production or args.mongo_uri else 'DEV'}")
    print(f"uri={_redact_uri(uri)}")

    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"CONNECT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.production:
            print(
                "Prod is typically VPC-only. Open an SSH tunnel, then set:\n"
                "  PRODUCTION_MONGO_URI=mongodb://skinbb:***@127.0.0.1:27018/skin_bb",
                file=sys.stderr,
            )
        raise SystemExit(1) from exc

    db_name = os.getenv("DB_NAME") or os.getenv("MONGODB_DATABASE") or "skin_bb"
    # Prefer DB from URI path when present
    path_db = (urlparse(uri).path or "").lstrip("/").split("?")[0]
    if path_db:
        db_name = path_db
    db = client[db_name]
    print(f"database={db_name}")

    before_b = _find_branded(db)
    before_i = _find_inci(db)
    print("BEFORE branded:", before_b)
    print("BEFORE inci:", before_i)

    if not before_b and not before_i:
        print("No Glyteine / Gamma-Glutamylcysteine docs found — aborting")
        raise SystemExit(2)

    if args.dry_run:
        print("dry-run: no writes")
        return

    now = datetime.now(timezone.utc)
    if before_b:
        r1 = db.ingre_branded_ingredients.update_one(
            {"_id": before_b["_id"]},
            {"$set": {"category_decided": "Active", "updatedAt": now}},
        )
        print(f"branded matched={r1.matched_count} modified={r1.modified_count} id={before_b['_id']}")
    else:
        print("branded: skipped (not found)")

    if before_i:
        r2 = db.ingre_inci.update_one(
            {"_id": before_i["_id"]},
            {"$set": {"category": "Active", "updatedAt": now}},
        )
        print(f"inci matched={r2.matched_count} modified={r2.modified_count} id={before_i['_id']}")
    else:
        print("inci: skipped (not found)")

    after_b = _find_branded(db)
    after_i = _find_inci(db)
    print("AFTER branded category_decided:", (after_b or {}).get("category_decided"))
    print("AFTER inci category:", (after_i or {}).get("category"))


if __name__ == "__main__":
    main()
