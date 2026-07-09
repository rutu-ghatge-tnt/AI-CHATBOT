"""Mongo persistence for HLHP Patterns v2 (state, patterns, narration, alerts)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.hlhp.db import hl_db
from app.hlhp.mongo_setup import ensure_hlhp_indexes
from app.hlhp.patterns.hlhp_patterns_engine import Pattern, PatternAlert, PatternState

logger = logging.getLogger(__name__)

_PATTERN_STATE = "hlhp_pattern_state"
_PATTERNS = "hlhp_patterns"
_NARRATION = "hlhp_narration_cache"
_ALERTS = "hlhp_pattern_alerts"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _pattern_state_from_doc(doc: dict[str, Any], user_id: str) -> PatternState:
    return PatternState(
        user_id=user_id,
        state=str(doc.get("state") or "LOCKED"),
        first_log_date=_parse_date(doc.get("first_log_date")),
        unlocked_at=doc.get("unlocked_at"),
        log_days_30=int(doc.get("log_days_30") or 0),
        exposure_days_30=int(doc.get("exposure_days_30") or 0),
        projected_unlock_date=_parse_date(doc.get("projected_unlock_date")),
        last_decay_notified_state=doc.get("last_decay_notified_state"),
        last_behind_pace_push_at=doc.get("last_behind_pace_push_at"),
        last_weekly_digest_at=doc.get("last_weekly_digest_at"),
        last_locked_push_d2_at=doc.get("last_locked_push_d2_at"),
    )


def _pattern_from_doc(doc: dict[str, Any]) -> Pattern | None:
    driver = doc.get("driver")
    symptom = doc.get("symptom")
    if not driver or not symptom:
        return None
    return Pattern(
        driver=str(driver),
        symptom=str(symptom),
        city=str(doc.get("city") or ""),
        E=int(doc.get("E") or 0),
        H=int(doc.get("H") or 0),
        match=float(doc.get("match") or 0),
        lift=float(doc.get("lift") or 0),
        label=str(doc.get("label") or "EARLY"),
        status=str(doc.get("status") or "promoted"),
        lag_hours=int(doc.get("lag_hours") or 24),
        zones=list(doc.get("zones") or []),
        weekday_hits=int(doc.get("weekday_hits") or 0),
        weekend_hits=int(doc.get("weekend_hits") or 0),
        library_cell_id=doc.get("library_cell_id"),
        pmids=list(doc.get("pmids") or []),
        first_detected=_parse_date(doc.get("first_detected")) or date.today(),
        last_confirmed=_parse_date(doc.get("last_confirmed")) or date.today(),
        chart=list(doc.get("chart") or []),
        weak_lift_days=int(doc.get("weak_lift_days") or 0),
    )


async def get_pattern_state(user_id: str) -> PatternState:
    await ensure_hlhp_indexes()
    if not user_id:
        return PatternState(
            user_id="",
            state="LOCKED",
            first_log_date=None,
            unlocked_at=None,
            log_days_30=0,
            exposure_days_30=0,
            projected_unlock_date=None,
        )
    try:
        doc = await hl_db[_PATTERN_STATE].find_one({"user_id": user_id})
        if doc:
            return _pattern_state_from_doc(doc, user_id)
    except Exception as exc:
        logger.warning("pattern_state fetch failed user=%s: %s", user_id, exc)
    return PatternState(
        user_id=user_id,
        state="LOCKED",
        first_log_date=None,
        unlocked_at=None,
        log_days_30=0,
        exposure_days_30=0,
        projected_unlock_date=None,
    )


async def save_pattern_state(ps: PatternState) -> None:
    await ensure_hlhp_indexes()
    if not ps.user_id:
        return
    doc: dict[str, Any] = {
        "user_id": ps.user_id,
        "state": ps.state,
        "first_log_date": ps.first_log_date.isoformat() if ps.first_log_date else None,
        "unlocked_at": ps.unlocked_at,
        "log_days_30": ps.log_days_30,
        "exposure_days_30": ps.exposure_days_30,
        "projected_unlock_date": (
            ps.projected_unlock_date.isoformat() if ps.projected_unlock_date else None
        ),
        "last_decay_notified_state": ps.last_decay_notified_state,
        "last_behind_pace_push_at": ps.last_behind_pace_push_at,
        "last_weekly_digest_at": ps.last_weekly_digest_at,
        "last_locked_push_d2_at": ps.last_locked_push_d2_at,
        "updated_at": _utcnow(),
    }
    try:
        await hl_db[_PATTERN_STATE].update_one(
            {"user_id": ps.user_id},
            {"$set": doc},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("pattern_state save failed user=%s: %s", ps.user_id, exc)


async def get_stored_patterns(user_id: str) -> list[Pattern]:
    await ensure_hlhp_indexes()
    if not user_id:
        return []
    out: list[Pattern] = []
    try:
        cursor = hl_db[_PATTERNS].find({"user_id": user_id})
        async for doc in cursor:
            pat = _pattern_from_doc(doc)
            if pat is not None:
                out.append(pat)
    except Exception as exc:
        logger.warning("patterns fetch failed user=%s: %s", user_id, exc)
    return out


async def save_patterns(user_id: str, patterns: list[Pattern]) -> None:
    await ensure_hlhp_indexes()
    if not user_id:
        return
    try:
        await hl_db[_PATTERNS].delete_many({"user_id": user_id})
        if not patterns:
            return
        docs = []
        for p in patterns:
            docs.append(
                {
                    "user_id": user_id,
                    "driver": p.driver,
                    "symptom": p.symptom,
                    "city": p.city,
                    "E": p.E,
                    "H": p.H,
                    "match": p.match,
                    "lift": p.lift,
                    "label": p.label,
                    "status": p.status,
                    "lag_hours": p.lag_hours,
                    "zones": p.zones,
                    "weekday_hits": p.weekday_hits,
                    "weekend_hits": p.weekend_hits,
                    "library_cell_id": p.library_cell_id,
                    "pmids": p.pmids,
                    "first_detected": p.first_detected.isoformat(),
                    "last_confirmed": p.last_confirmed.isoformat(),
                    "chart": p.chart,
                    "weak_lift_days": p.weak_lift_days,
                    "updated_at": _utcnow(),
                }
            )
        if docs:
            await hl_db[_PATTERNS].insert_many(docs)
    except Exception as exc:
        logger.warning("patterns save failed user=%s: %s", user_id, exc)


async def set_first_log_date_if_missing(user_id: str, first: date) -> None:
    await ensure_hlhp_indexes()
    if not user_id:
        return
    try:
        doc = await hl_db[_PATTERN_STATE].find_one({"user_id": user_id})
        if doc and doc.get("first_log_date"):
            return
        await hl_db[_PATTERN_STATE].update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "first_log_date": first.isoformat(),
                    "updated_at": _utcnow(),
                }
            },
            upsert=True,
        )
    except Exception as exc:
        logger.warning("first_log_date set failed user=%s: %s", user_id, exc)


async def get_narration_cache(user_id: str) -> dict[str, Any]:
    await ensure_hlhp_indexes()
    if not user_id:
        return {}
    try:
        cursor = hl_db[_NARRATION].find({"user_id": user_id})
        patterns: list[dict[str, Any]] = []
        unlock_headline = None
        unlock_identity = None
        weekly_digest = None
        async for doc in cursor:
            kind = str(doc.get("kind") or "")
            if kind == "pattern":
                patterns.append(
                    {
                        "id": doc.get("pattern_id"),
                        "say": doc.get("say", ""),
                        "plain": doc.get("plain", ""),
                        "cc_note": doc.get("cc_note", ""),
                    }
                )
            elif kind == "unlock_headline":
                unlock_headline = doc.get("text")
            elif kind == "unlock_identity":
                unlock_identity = doc.get("text")
            elif kind == "weekly_digest":
                weekly_digest = doc.get("text")
        out: dict[str, Any] = {}
        if patterns:
            out["patterns"] = patterns
        if unlock_headline:
            out["unlock_headline"] = unlock_headline
        if unlock_identity:
            out["unlock_identity"] = unlock_identity
        if weekly_digest:
            out["weekly_digest"] = weekly_digest
        return out
    except Exception as exc:
        logger.warning("narration cache fetch failed user=%s: %s", user_id, exc)
        return {}


async def save_narration_entry(
    user_id: str,
    *,
    kind: str,
    text: str,
    pattern_id: str | None = None,
    say: str | None = None,
    plain: str | None = None,
    cc_note: str | None = None,
    input_hash: str | None = None,
    valid: bool = True,
) -> None:
    await ensure_hlhp_indexes()
    if not user_id:
        return
    filt: dict[str, Any] = {"user_id": user_id, "kind": kind}
    if pattern_id:
        filt["pattern_id"] = pattern_id
    doc: dict[str, Any] = {
        **filt,
        "text": text,
        "say": say,
        "plain": plain,
        "cc_note": cc_note,
        "input_hash": input_hash,
        "valid": valid,
        "generated_at": _utcnow(),
    }
    try:
        await hl_db[_NARRATION].update_one(filt, {"$set": doc}, upsert=True)
    except Exception as exc:
        logger.warning("narration cache save failed user=%s: %s", user_id, exc)


async def get_pattern_alerts(user_id: str) -> list[PatternAlert]:
    await ensure_hlhp_indexes()
    if not user_id:
        return []
    out: list[PatternAlert] = []
    try:
        cursor = hl_db[_ALERTS].find({"user_id": user_id})
        async for doc in cursor:
            out.append(
                PatternAlert(
                    user_id=user_id,
                    pattern_id=str(doc["pattern_id"]),
                    driver=str(doc["driver"]),
                    symptom=str(doc["symptom"]),
                    created_at=doc.get("created_at") or _utcnow(),
                    last_fired_on=_parse_date(doc.get("last_fired_on")),
                    active=bool(doc.get("active", True)),
                )
            )
    except Exception as exc:
        logger.warning("pattern alerts fetch failed user=%s: %s", user_id, exc)
    return out


async def save_pattern_alerts(user_id: str, alerts: list[PatternAlert]) -> None:
    await ensure_hlhp_indexes()
    if not user_id:
        return
    try:
        await hl_db[_ALERTS].delete_many({"user_id": user_id})
        if not alerts:
            return
        docs = [
            {
                "user_id": user_id,
                "pattern_id": a.pattern_id,
                "driver": a.driver,
                "symptom": a.symptom,
                "created_at": a.created_at,
                "last_fired_on": a.last_fired_on.isoformat() if a.last_fired_on else None,
                "active": a.active,
            }
            for a in alerts
        ]
        await hl_db[_ALERTS].insert_many(docs)
    except Exception as exc:
        logger.warning("pattern alerts save failed user=%s: %s", user_id, exc)
