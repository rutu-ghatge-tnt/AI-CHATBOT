#!/usr/bin/env python3
"""Collect HLHP city weather + V4 SFI into permanent Mongo archives.

Examples:
  python scripts/collect_hlhp_city_env.py --board
  python scripts/collect_hlhp_city_env.py --board --backfill-days 30
  python scripts/collect_hlhp_city_env.py --off-board
  python scripts/collect_hlhp_city_env.py --board --off-board
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    """Load repo .env before any app/hlhp imports that read os.environ."""
    env_path = ROOT / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        print(
            "python-dotenv not installed — set MONGO_URI and WEATHERAPI_KEY in the shell",
            file=sys.stderr,
        )
        return
    load_dotenv(env_path)


def _preflight() -> None:
    mongo = (os.getenv("MONGO_URI") or os.getenv("PRODUCTION_MONGO_URI") or "").strip()
    weather = (os.getenv("WEATHERAPI_KEY") or os.getenv("WEATHER_API_KEY") or "").strip()
    missing: list[str] = []
    if not mongo:
        missing.append("MONGO_URI (or PRODUCTION_MONGO_URI)")
    if not weather:
        missing.append("WEATHERAPI_KEY (or WEATHER_API_KEY)")
    if missing:
        print(
            "Missing required env after loading .env:\n  - " + "\n  - ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1)


async def _run(args: argparse.Namespace) -> int:
    from app.hlhp.mongo_setup import ensure_hlhp_indexes
    from app.hlhp.services.city_env_jobs import (
        backfill_fixed_board,
        collect_fixed_board,
        collect_off_board_recent,
    )

    await ensure_hlhp_indexes()
    out: dict = {}

    if args.backfill_days:
        out["backfill"] = await backfill_fixed_board(days=int(args.backfill_days))
    elif args.board:
        out["board"] = await collect_fixed_board()

    if args.off_board:
        out["off_board"] = await collect_off_board_recent(
            lookback_days=int(args.off_board_lookback)
        )

    if not out:
        print("Nothing to do — pass --board and/or --off-board", file=sys.stderr)
        return 2

    print(json.dumps(out, default=str, indent=2))
    board = out.get("board") or out.get("backfill") or {}
    ok = int(board.get("ok_day_writes") or 0)
    if board and ok == 0:
        print(
            "WARNING: 0 successful day writes — check WeatherAPI responses / network",
            file=sys.stderr,
        )
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect HLHP city env daily+slot rows")
    parser.add_argument(
        "--board",
        action="store_true",
        help="Collect fixed 11-city board for yesterday+today (IST)",
    )
    parser.add_argument(
        "--backfill-days",
        type=int,
        default=0,
        help="Backfill N IST days for the fixed board (implies board)",
    )
    parser.add_argument(
        "--off-board",
        action="store_true",
        help="Refresh recently seen 12th/off-board cities",
    )
    parser.add_argument(
        "--off-board-lookback",
        type=int,
        default=7,
        help="Days of off-board history to consider for refresh (default 7)",
    )
    args = parser.parse_args()
    if args.backfill_days and not args.board:
        args.board = True

    _load_env()
    _preflight()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
