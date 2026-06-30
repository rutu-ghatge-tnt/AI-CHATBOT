"""Append-only HLHP user log events (symptoms + environment snapshot)."""



from __future__ import annotations



import logging

from datetime import datetime, timezone

from typing import Any



from app.hlhp.db import hl_db

from app.hlhp.db_errors import fail_write

from app.hlhp.mongo_setup import ensure_hlhp_indexes



logger = logging.getLogger(__name__)



_LOG_EVENTS = "hlhp_user_log_events"





def _parse_dt(value) -> datetime:

    if isinstance(value, datetime):

        if value.tzinfo is None:

            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    return datetime.now(timezone.utc)





async def insert_log_event(doc: dict[str, Any]) -> None:

    if not doc.get("user_id"):

        return

    await ensure_hlhp_indexes()

    try:

        await hl_db[_LOG_EVENTS].insert_one(doc)

    except Exception as exc:

        fail_write(_LOG_EVENTS, "insert", exc)





async def fetch_latest_log_for_date(user_id: str, date_key: str) -> dict[str, Any] | None:

    """Most recent log event for a calendar day (symptoms + areas)."""

    if not user_id or not date_key:

        return None

    await ensure_hlhp_indexes()

    try:

        return await hl_db[_LOG_EVENTS].find_one(

            {"user_id": user_id, "date": date_key},

            sort=[("ts", -1)],

        )

    except Exception as exc:

        logger.warning("HLHP user_log_events latest fetch failed: %s", exc)

        return None





async def fetch_log_event_dates(user_id: str, *, limit: int = 400) -> set[str]:

    if not user_id:

        return set()

    await ensure_hlhp_indexes()

    dates: set[str] = set()

    try:

        cursor = (

            hl_db[_LOG_EVENTS]

            .find({"user_id": user_id}, {"date": 1})

            .sort("ts", -1)

            .limit(limit)

        )

        async for doc in cursor:

            day = str(doc.get("date") or "")

            if day:

                dates.add(day)

    except Exception as exc:

        logger.warning("HLHP user_log_events fetch failed: %s", exc)

    return dates





async def count_log_events(user_id: str) -> int:

    if not user_id:

        return 0

    await ensure_hlhp_indexes()

    try:

        return await hl_db[_LOG_EVENTS].count_documents({"user_id": user_id})

    except Exception as exc:

        logger.warning("HLHP user_log_events count failed: %s", exc)

        return 0


