from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId

from app.hlhp.coach.models import ActionRecord, CoachContext, StreakRecord
from app.hlhp.coach.streak_engine import compute_streak_after_tap, current_streak, streak_key
from app.hlhp.coach.voice_modulator import select_tone
from app.hlhp.db import hl_db
from app.hlhp.models.profile import UserProfile
from app.hlhp.services.profile_loader import load_user_first_name

logger = logging.getLogger(__name__)

_ACTIONS = "hlhp_action_log"
_STREAKS = "hlhp_streak_counters"
_SURFACED = "hlhp_surfaced_rule_log"
_NUGGETS = "hlhp_nugget_log"
_SYMPTOMS = "hlhp_symptom_tap_log"


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.now(timezone.utc)


async def _load_user_name(user_id: str) -> str:
    return await load_user_first_name(user_id)


async def load_coach_context(
    user_id: str,
    profile: UserProfile,
    *,
    local_time: datetime,
    severity: str = "SOFT_ENV",
) -> CoachContext:
    since_7d = local_time - timedelta(days=7)
    since_5d = local_time - timedelta(days=5)
    since_14d = local_time - timedelta(days=14)

    actions_col = hl_db[_ACTIONS]
    streaks_col = hl_db[_STREAKS]
    surfaced_col = hl_db[_SURFACED]
    nuggets_col = hl_db[_NUGGETS]
    symptoms_col = hl_db[_SYMPTOMS]

    recent_actions: list[ActionRecord] = []
    streaks: dict[str, StreakRecord] = {}
    suppressed: set[str] = set()
    archetypes: set[str] = set()
    seen_nuggets: set[int] = set()
    last_symptom: Optional[str] = None
    last_symptom_at: Optional[datetime] = None

    try:
        async for doc in actions_col.find(
            {"user_id": user_id, "tapped_at": {"$gte": since_7d}}
        ).sort("tapped_at", -1):
            recent_actions.append(
                ActionRecord(
                    routine_action=doc.get("routine_action", ""),
                    tapped_at=_parse_dt(doc.get("tapped_at")),
                    rule_id_context=doc.get("rule_id_context"),
                )
            )

        async for doc in streaks_col.find({"user_id": user_id}):
            key = doc.get("streak_key", "")
            streaks[key] = StreakRecord(
                streak_key=key,
                consecutive_days=int(doc.get("consecutive_days", 0)),
                last_increment_at=_parse_dt(doc["last_increment_at"])
                if doc.get("last_increment_at")
                else None,
                longest_ever=int(doc.get("longest_ever", 0)),
            )

        async for doc in surfaced_col.find(
            {"user_id": user_id, "surfaced_at": {"$gte": since_5d}}
        ):
            rid = doc.get("rule_id")
            if rid:
                suppressed.add(rid)
            arch = doc.get("archetype")
            if arch:
                archetypes.add(str(arch).upper())

        async for doc in nuggets_col.find(
            {"user_id": user_id, "shown_at": {"$gte": since_14d}}
        ):
            nid = doc.get("nugget_id")
            if nid is not None:
                seen_nuggets.add(int(nid))

        symptom_doc = await symptoms_col.find_one(
            {"user_id": user_id},
            sort=[("tapped_at", -1)],
        )
        if symptom_doc:
            last_symptom = symptom_doc.get("symptom_keyword")
            last_symptom_at = _parse_dt(symptom_doc.get("tapped_at"))
    except Exception as exc:
        logger.warning("HLHP coach state load failed for %s: %s", user_id, exc)

    name = await _load_user_name(user_id)
    return CoachContext(
        user_id=user_id,
        name=name,
        tone=select_tone(profile, severity=severity),
        recent_actions=recent_actions,
        streaks=streaks,
        suppressed_rule_ids=suppressed,
        recent_archetypes=archetypes,
        seen_nugget_ids=seen_nuggets,
        last_symptom_keyword=last_symptom,
        last_symptom_at=last_symptom_at,
    )


async def record_surfaced_rules(
    user_id: str,
    findings: list,
    *,
    surfaced_at: datetime | None = None,
) -> None:
    when = surfaced_at or datetime.now(timezone.utc)
    docs = [
        {
            "user_id": user_id,
            "rule_id": f.id,
            "archetype": f.engagement_archetype or "",
            "surfaced_at": when,
        }
        for f in findings
    ]
    if not docs:
        return
    try:
        await hl_db[_SURFACED].insert_many(docs)
    except Exception as exc:
        logger.warning("HLHP surfaced_rule_log write failed: %s", exc)


async def record_nugget_shown(user_id: str, nugget_id: int) -> None:
    try:
        await hl_db[_NUGGETS].insert_one(
            {
                "user_id": user_id,
                "nugget_id": nugget_id,
                "shown_at": datetime.now(timezone.utc),
            }
        )
    except Exception as exc:
        logger.warning("HLHP nugget_log write failed: %s", exc)


async def record_action_tap(
    user_id: str,
    *,
    routine_action: str,
    uvi_band: str,
    tapped_at: datetime,
    rule_id: Optional[str] = None,
) -> tuple[int, int]:
    skey = streak_key(uvi_band, routine_action)
    streaks_col = hl_db[_STREAKS]
    existing = await streaks_col.find_one({"user_id": user_id, "streak_key": skey})

    prior = None
    if existing:
        prior = StreakRecord(
            streak_key=skey,
            consecutive_days=int(existing.get("consecutive_days", 0)),
            last_increment_at=_parse_dt(existing["last_increment_at"])
            if existing.get("last_increment_at")
            else None,
            longest_ever=int(existing.get("longest_ever", 0)),
        )

    updated = compute_streak_after_tap(
        prior, streak_key_val=skey, today=tapped_at.date(), tapped_at=tapped_at
    )

    try:
        await hl_db[_ACTIONS].insert_one(
            {
                "user_id": user_id,
                "routine_action": routine_action,
                "tapped_at": tapped_at,
                "rule_id_context": rule_id,
            }
        )
        await streaks_col.update_one(
            {"user_id": user_id, "streak_key": skey},
            {
                "$set": {
                    "consecutive_days": updated.consecutive_days,
                    "last_increment_at": updated.last_increment_at,
                    "longest_ever": updated.longest_ever,
                }
            },
            upsert=True,
        )
    except Exception as exc:
        logger.warning("HLHP action_tap persist failed: %s", exc)

    today = tapped_at.date()
    return current_streak(updated, today), updated.longest_ever


_FEELINGS = "hlhp_symptom_feeling_log"


async def _latest_feeling_state(
    user_id: str,
    *,
    since: datetime | None = None,
) -> dict[str, bool]:
    """Keyword -> selected as of the most recent toggle (insert-only log)."""
    if not user_id:
        return {}
    query: dict = {"user_id": user_id}
    if since is not None:
        query["recorded_at"] = {"$gte": since}
    try:
        cursor = hl_db[_FEELINGS].find(query).sort("recorded_at", 1)
        by_kw: dict[str, bool] = {}
        async for doc in cursor:
            kw = str(doc.get("symptom_keyword") or "").strip().lower()
            if kw:
                by_kw[kw] = bool(doc.get("selected"))
        return by_kw
    except Exception as exc:
        logger.warning("HLHP symptom_feeling state fetch failed: %s", exc)
        return {}


async def fetch_selected_symptoms(
    user_id: str,
    *,
    days: int = 30,
) -> set[str]:
    """Keywords the user actively selected (latest toggle wins per keyword)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    state = await _latest_feeling_state(user_id, since=since)
    return {kw for kw, selected in state.items() if selected}


async def fetch_daily_feeling_keywords(
    user_id: str,
    *,
    since: datetime,
) -> dict[str, list[str]]:
    """ISO date -> symptom keywords selected as of end of that day (latest toggle wins)."""
    if not user_id:
        return {}
    try:
        cursor = hl_db[_FEELINGS].find(
            {"user_id": user_id, "recorded_at": {"$gte": since}},
        ).sort("recorded_at", 1)
        by_date_kw: dict[str, dict[str, bool]] = {}
        async for doc in cursor:
            recorded = doc.get("recorded_at")
            if isinstance(recorded, datetime):
                if recorded.tzinfo is None:
                    recorded = recorded.replace(tzinfo=timezone.utc)
                else:
                    recorded = recorded.astimezone(timezone.utc)
            else:
                continue
            day = recorded.date().isoformat()
            kw = str(doc.get("symptom_keyword") or "").strip().lower()
            if not kw:
                continue
            by_date_kw.setdefault(day, {})[kw] = bool(doc.get("selected"))
        return {
            day: sorted(k for k, selected in kws.items() if selected)
            for day, kws in by_date_kw.items()
        }
    except Exception as exc:
        logger.warning("HLHP symptom_feeling daily fetch failed: %s", exc)
        return {}


async def record_symptom_feeling(
    user_id: str,
    symptom_keyword: str,
    *,
    selected: bool,
    recorded_at: datetime,
) -> None:
    try:
        await hl_db[_FEELINGS].insert_one(
            {
                "user_id": user_id,
                "symptom_keyword": symptom_keyword.strip().lower(),
                "selected": selected,
                "recorded_at": recorded_at,
            }
        )
    except Exception as exc:
        logger.warning("HLHP symptom_feeling write failed: %s", exc)


async def record_symptom_tap(user_id: str, symptom_keyword: str, tapped_at: datetime) -> None:
    try:
        await hl_db[_SYMPTOMS].insert_one(
            {
                "user_id": user_id,
                "symptom_keyword": symptom_keyword,
                "tapped_at": tapped_at,
            }
        )
    except Exception as exc:
        logger.warning("HLHP symptom_tap_log write failed: %s", exc)
