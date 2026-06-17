#!/usr/bin/env python3
"""
Pre-analyze catalog products into Mongo `product_analyses`.

Skips products that already have a successful analysis unless --force is passed.
Only processes products missing from the store by default (incremental for new PDPs).

Usage (development — uses .env MONGO_URI):
  python scripts/batch_analyze_products.py --dry-run --limit 10

Usage (production — required for good catalog data):

  Direct (only from VPC / VPN — 10.0.128.233 is NOT reachable from a home PC):
  set PRODUCTION_MONGO_URI=mongodb://user:pass@10.0.128.233:27017/skin_bb
  python scripts/batch_analyze_products.py --production --dry-run --limit 10

  SSH tunnel (run from your laptop):
  ssh -L 27018:10.0.128.233:27017 user@<bastion-or-vps>
  python scripts/batch_analyze_products.py --production ^
    --mongo-uri "mongodb://skinbb:***@127.0.0.1:27018/skin_bb" ^
    --dry-run --limit 10

  Or run the script ON the production VPS (same network as Mongo).

The script refuses to run against the development VPS (93.127.194.42)
unless you pass --allow-dev explicitly.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Development Mongo — never use for batch catalog pre-analysis.
_DEV_VPS_HOSTS = frozenset({"93.127.194.42"})

# Localhost is allowed in --production when using an SSH tunnel to prod.
_LOCAL_MONGO_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Expected production catalog host (private VPC). Used for confirmation messaging only.
_PROD_MONGO_HOSTS = frozenset({"10.0.128.233"})


def _mongo_host(uri: str) -> str:
    parsed = urlparse(uri)
    host = (parsed.hostname or "").strip().lower()
    if not host and "@" in uri:
        tail = uri.rsplit("@", 1)[-1]
        host = (urlparse(f"mongodb://{tail}").hostname or "").strip().lower()
    return host


def _redact_mongo_uri(uri: str) -> str:
    if not uri:
        return ""
    return re.sub(r"://([^:@/]+):([^@/]+)@", r"://\1:***@", uri)


def _configure_mongo(*, uri: str, database: str | None) -> None:
    os.environ["MONGO_URI"] = uri
    os.environ["MONGODB_URI"] = uri
    if database:
        os.environ["DB_NAME"] = database
        os.environ["MONGODB_DATABASE"] = database

    from app.label_looker.core.db import _client
    from app.label_looker.core.settings import get_label_looker_settings

    get_label_looker_settings.cache_clear()
    _client.cache_clear()


def _resolve_mongo_target(args: argparse.Namespace) -> tuple[str, str]:
    uri = (args.mongo_uri or "").strip()
    database = (args.database or "").strip() or None

    if args.production:
        if not uri:
            uri = (os.getenv("PRODUCTION_MONGO_URI") or os.getenv("PROD_MONGO_URI") or "").strip()
        if not uri:
            raise SystemExit(
                "Production mode requires --mongo-uri or PRODUCTION_MONGO_URI in the environment.\n"
                "Example:\n"
                '  set PRODUCTION_MONGO_URI=mongodb://skinbb:***@10.0.128.233:27017/skin_bb\n'
                "  python scripts/batch_analyze_products.py --production --dry-run --limit 5"
            )
        if not database:
            parsed = urlparse(uri)
            database = (parsed.path or "").lstrip("/") or "skin_bb"
    else:
        if uri:
            if not database:
                parsed = urlparse(uri)
                database = (parsed.path or "").lstrip("/") or None
        else:
            uri = (os.getenv("MONGODB_URI") or os.getenv("MONGO_URI") or "").strip()
            database = database or (os.getenv("MONGODB_DATABASE") or os.getenv("DB_NAME") or "skin_bb").strip()

    if not uri:
        raise SystemExit("No MongoDB URI. Set MONGO_URI in .env or pass --mongo-uri / --production.")

    host = _mongo_host(uri)
    is_dev_vps = host in _DEV_VPS_HOSTS
    is_local = host in _LOCAL_MONGO_HOSTS
    is_prod_host = host in _PROD_MONGO_HOSTS

    if args.production and is_dev_vps:
        raise SystemExit(
            f"Refusing production run: URI host {host!r} is the development VPS.\n"
            "Use production skin_bb (10.0.128.233) or an SSH tunnel to it."
        )

    if not args.production and (is_dev_vps or is_local) and not args.allow_dev:
        raise SystemExit(
            f"Refusing to run: MONGO_URI points to host {host!r}.\n"
            "Product data on dev/local is incomplete. Use one of:\n"
            "  python scripts/batch_analyze_products.py --production --mongo-uri <prod-uri> ...\n"
            "  python scripts/batch_analyze_products.py --allow-dev ...   # only if you really mean dev"
        )

    if args.production and is_local:
        logger.warning(
            "Production mode via localhost — assuming SSH tunnel to prod Mongo. Database must be skin_bb."
        )

    if args.production and not is_prod_host and not is_local:
        logger.warning(
            "Production mode: host %s is not the usual prod host %s — continuing because --production was set.",
            host,
            ", ".join(sorted(_PROD_MONGO_HOSTS)),
        )

    return uri, database or "skin_bb"


async def _verify_mongo_connection(*, uri: str, database: str, production: bool) -> None:
    from pymongo.errors import ServerSelectionTimeoutError

    from app.label_looker.core.db import get_scanner_db

    host = _mongo_host(uri)
    try:
        db = get_scanner_db()
        await db.command("ping")
        count = await db["products"].estimated_document_count()
        logger.info("Mongo connected: database=%s products≈%s", database, count)
    except ServerSelectionTimeoutError:
        lines = [
            f"Cannot reach MongoDB at {host!r} (connection timed out).",
            "",
        ]
        if host in _PROD_MONGO_HOSTS:
            lines.extend(
                [
                    "10.0.128.233 is a private VPC address — not reachable from most laptops.",
                    "",
                    "Fix options:",
                    "  1) Connect VPN to the production network, then retry.",
                    "  2) SSH tunnel, then use localhost:",
                    "       ssh -L 27018:10.0.128.233:27017 user@<bastion>",
                    '       python scripts/batch_analyze_products.py --production --mongo-uri "mongodb://USER:PASS@127.0.0.1:27018/skin_bb" ...',
                    "  3) SSH into the production VPS and run this script there.",
                ]
            )
        elif host in _LOCAL_MONGO_HOSTS and production:
            lines.extend(
                [
                    "You are using --production with localhost — start the SSH tunnel first:",
                    "  ssh -L 27018:10.0.128.233:27017 user@<bastion>",
                    '  --mongo-uri "mongodb://USER:PASS@127.0.0.1:27018/skin_bb"',
                ]
            )
        else:
            lines.append("Check VPN, firewall, credentials, and that Mongo is listening.")
        raise SystemExit("\n".join(lines)) from None
    except Exception as exc:
        raise SystemExit(f"Mongo connection failed ({host}): {exc}") from exc


async def _run(args: argparse.Namespace) -> int:
    uri, database = _resolve_mongo_target(args)
    _configure_mongo(uri=uri, database=database)

    from bson import ObjectId

    from app.label_looker.core.db import get_scanner_db
    from app.label_looker.core.settings import get_label_looker_settings
    from app.label_looker.services.product_analysis_engine import analyze_catalog_product
    from app.label_looker.services.product_analysis_store import list_analyzed_product_ids

    s = get_label_looker_settings()
    host = _mongo_host(uri)
    logger.info(
        "Mongo target: host=%s database=%s uri=%s production=%s",
        host,
        database,
        _redact_mongo_uri(uri),
        bool(args.production),
    )

    await _verify_mongo_connection(uri=uri, database=database, production=bool(args.production))
    if args.check_connection:
        logger.info("Connection OK — exiting (--check-connection)")
        return 0

    db = get_scanner_db()
    products_coll = db[s.coll_products]
    branded_coll = db[s.coll_branded_ingredient]
    ingredient_coll = db[s.coll_ingredient]
    product_analysis_coll = db[s.coll_product_analysis]

    analyzed_ids: set[str] = set()
    if not args.force and not args.product_id:
        analyzed_ids = await list_analyzed_product_ids(coll=product_analysis_coll)
        logger.info("Already analyzed: %s products", len(analyzed_ids))

    if args.product_id:
        pid = str(args.product_id).strip()
        query = {"_id": ObjectId(pid)} if ObjectId.is_valid(pid) else {"_id": pid}
        products = await products_coll.find(query).to_list(length=1)
    else:
        query: dict = {}
        cursor = products_coll.find(query).sort("_id", 1)
        if args.limit:
            cursor = cursor.limit(int(args.limit))
        products = await cursor.to_list(length=args.limit or 10_000)

    stats = {"total": 0, "skipped": 0, "analyzed": 0, "failed": 0, "dry_run": 0}

    for product in products:
        stats["total"] += 1
        pid = product.get("_id")
        pid_str = str(pid)
        name = product.get("productName") or product.get("name") or pid_str

        if not args.force and pid_str in analyzed_ids:
            stats["skipped"] += 1
            logger.info("skip (already analyzed): %s — %s", pid_str, name)
            continue

        if args.dry_run:
            stats["dry_run"] += 1
            logger.info("dry-run would analyze: %s — %s", pid_str, name)
            continue

        try:
            result = await analyze_catalog_product(
                product=product,
                products_coll=products_coll,
                branded_ingredients_coll=branded_coll,
                ingredient_coll=ingredient_coll,
                product_analysis_coll=product_analysis_coll,
                force=bool(args.force),
                source="batch",
            )
            if result.get("skipped"):
                stats["skipped"] += 1
                logger.info("skip (%s): %s — %s", result.get("reason"), pid_str, name)
            else:
                stats["analyzed"] += 1
                logger.info("analyzed: %s — %s (%s ingredients)", pid_str, name, result.get("ingredientCount"))
        except Exception as exc:
            stats["failed"] += 1
            logger.exception("failed: %s — %s: %s", pid_str, name, exc)

    logger.info(
        "done total=%s analyzed=%s skipped=%s failed=%s dry_run=%s",
        stats["total"],
        stats["analyzed"],
        stats["skipped"],
        stats["failed"],
        stats["dry_run"],
    )
    return 1 if stats["failed"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch pre-analyze catalog products for Label Looker")
    parser.add_argument("--limit", type=int, default=0, help="Max products to scan from catalog (0 = no limit)")
    parser.add_argument("--product-id", type=str, default="", help="Analyze one product by Mongo _id")
    parser.add_argument("--force", action="store_true", help="Re-analyze even when product_analyses row exists")
    parser.add_argument("--dry-run", action="store_true", help="List work only; do not call Claude")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use production Mongo (PRODUCTION_MONGO_URI or --mongo-uri). Blocks dev hosts.",
    )
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default="",
        help="Mongo connection string override (use with --production for prod catalog)",
    )
    parser.add_argument(
        "--database",
        type=str,
        default="",
        help="Database name override (default: parsed from URI or skin_bb)",
    )
    parser.add_argument(
        "--allow-dev",
        action="store_true",
        help="Allow running against development Mongo (93.127.194.42 / localhost)",
    )
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="Only test Mongo connectivity and exit (no product analysis)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
