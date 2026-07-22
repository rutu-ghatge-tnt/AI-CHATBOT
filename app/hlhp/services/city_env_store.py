"""Permanent city weather + V4 SFI archive (daily + slot). No TTL — training spine."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.hlhp.db import hl_db
from app.hlhp.mongo_setup import ensure_hlhp_indexes

logger = logging.getLogger(__name__)

CITY_ENV_DAILY = "hlhp_city_env_daily"
CITY_ENV_SLOT = "hlhp_city_env_slot"
CITY_ENV_TZ = "Asia/Kolkata"
SCORING_VERSION = "v4"


def city_key_from_label(label: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")
    return cleaned[:80] or "unknown"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_city_env_slot(doc: dict[str, Any]) -> None:
    """Upsert one city × date × slot_hour row."""
    city_key = str(doc.get("city_key") or "").strip()
    date_key = str(doc.get("date") or "").strip()
    slot_hour = doc.get("slot_hour")
    if not city_key or not date_key or slot_hour is None:
        return
    await ensure_hlhp_indexes()
    payload = {**doc, "updated_at": _now_utc()}
    payload.setdefault("tz", CITY_ENV_TZ)
    payload.setdefault("scoring_version", SCORING_VERSION)
    try:
        await hl_db[CITY_ENV_SLOT].update_one(
            {
                "city_key": city_key,
                "date": date_key,
                "slot_hour": int(slot_hour),
            },
            {"$set": payload, "$setOnInsert": {"created_at": _now_utc()}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(
            "HLHP city_env_slot upsert failed city=%s date=%s hour=%s: %s",
            city_key,
            date_key,
            slot_hour,
            exc,
        )


async def upsert_city_env_daily(doc: dict[str, Any]) -> None:
    """Upsert one city × date row (rollup of slots)."""
    city_key = str(doc.get("city_key") or "").strip()
    date_key = str(doc.get("date") or "").strip()
    if not city_key or not date_key:
        return
    await ensure_hlhp_indexes()
    payload = {**doc, "updated_at": _now_utc()}
    payload.setdefault("tz", CITY_ENV_TZ)
    payload.setdefault("scoring_version", SCORING_VERSION)
    try:
        await hl_db[CITY_ENV_DAILY].update_one(
            {"city_key": city_key, "date": date_key},
            {"$set": payload, "$setOnInsert": {"created_at": _now_utc()}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(
            "HLHP city_env_daily upsert failed city=%s date=%s: %s",
            city_key,
            date_key,
            exc,
        )


async def fetch_city_env_daily(
    city_key: str,
    *,
    date_from: str,
    date_to: str,
    limit: int = 400,
) -> list[dict[str, Any]]:
    if not city_key:
        return []
    await ensure_hlhp_indexes()
    try:
        cursor = (
            hl_db[CITY_ENV_DAILY]
            .find(
                {
                    "city_key": city_key,
                    "date": {"$gte": date_from, "$lte": date_to},
                }
            )
            .sort("date", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]
    except Exception as exc:
        logger.warning("HLHP city_env_daily fetch failed: %s", exc)
        return []


async def fetch_city_env_slots(
    city_key: str,
    *,
    date_key: str,
) -> list[dict[str, Any]]:
    if not city_key or not date_key:
        return []
    await ensure_hlhp_indexes()
    try:
        cursor = (
            hl_db[CITY_ENV_SLOT]
            .find({"city_key": city_key, "date": date_key})
            .sort("slot_hour", 1)
        )
        return [doc async for doc in cursor]
    except Exception as exc:
        logger.warning("HLHP city_env_slot fetch failed: %s", exc)
        return []


async def list_recent_off_board_cities(*, since_date: str, limit: int = 50) -> list[str]:
    """Distinct off-board city_keys seen on/after since_date (for refresh jobs)."""
    await ensure_hlhp_indexes()
    try:
        rows = await hl_db[CITY_ENV_DAILY].distinct(
            "city_key",
            {"on_board": False, "date": {"$gte": since_date}},
        )
        out = [str(r) for r in rows if r]
        return out[:limit]
    except Exception as exc:
        logger.warning("HLHP off-board city list failed: %s", exc)
        return []
