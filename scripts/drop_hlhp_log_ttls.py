#!/usr/bin/env python3
"""Drop legacy Mongo TTL indexes on HLHP training-critical log collections.

App startup also does this via ensure_hlhp_indexes(). Use this script to verify
or to run the drop without booting the full API.

  python scripts/drop_hlhp_log_ttls.py
  python scripts/drop_hlhp_log_ttls.py --list-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    if env_path.is_file():
        load_dotenv(env_path)


async def _list_ttls() -> dict[str, list[dict]]:
    from app.hlhp.db import hl_db
    from app.hlhp.mongo_setup import _PERMANENT_LOG_COLLECTIONS

    out: dict[str, list[dict]] = {}
    for name in _PERMANENT_LOG_COLLECTIONS:
        rows: list[dict] = []
        async for idx in hl_db[name].list_indexes():
            if idx.get("expireAfterSeconds") is None:
                continue
            rows.append(
                {
                    "name": idx.get("name"),
                    "key": dict(idx.get("key") or {}),
                    "expireAfterSeconds": idx.get("expireAfterSeconds"),
                }
            )
        out[name] = rows
        # Also check outbox (should KEEP ttl)
    outbox_ttls: list[dict] = []
    async for idx in hl_db["hlhp_pattern_notification_outbox"].list_indexes():
        if idx.get("expireAfterSeconds") is None:
            continue
        outbox_ttls.append(
            {
                "name": idx.get("name"),
                "key": dict(idx.get("key") or {}),
                "expireAfterSeconds": idx.get("expireAfterSeconds"),
            }
        )
    out["hlhp_pattern_notification_outbox (keep)"] = outbox_ttls
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description="Drop HLHP permanent-log TTL indexes")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only print TTL indexes; do not drop",
    )
    args = parser.parse_args()
    _load_env()

    print("TTL indexes before:")
    print(json.dumps(await _list_ttls(), indent=2))

    if args.list_only:
        return 0

    from app.hlhp.mongo_setup import drop_permanent_log_ttls

    results = await drop_permanent_log_ttls()
    print("Dropped counts:", json.dumps(results, indent=2))
    print("TTL indexes after:")
    print(json.dumps(await _list_ttls(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
