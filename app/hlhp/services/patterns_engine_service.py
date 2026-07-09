"""Patterns v2 — adapter from Mongo log stores to hlhp_patterns_engine."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.core.local_date import today_local
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.patterns.band_bridge import daily_doc_band_keys, scenario_master_key
from app.hlhp.patterns.hlhp_patterns_engine import (
    Config,
    DailyLog,
    EnvDay,
    Pattern,
    PatternAlert,
    PatternState,
    build_patterns_payload,
    detect_patterns,
    evaluate_state,
    is_subscribed,
    pattern_to_card,
    subscribe_alert,
    unsubscribe_alert,
)
from app.hlhp.services.concern_resolver import resolve_concern_id
from app.hlhp.services.daily_log_store import RETENTION_DAYS, fetch_daily_logs
from app.hlhp.services.history_service import _latest_feelings_by_day_from_sessions
from app.hlhp.services.log_event_store import fetch_log_event_dates, fetch_log_events
from app.hlhp.services.pattern_state_store import (
    get_pattern_alerts,
    get_pattern_state,
    get_stored_patterns,
    save_pattern_alerts,
    save_pattern_state,
    save_patterns,
    set_first_log_date_if_missing,
)
from app.hlhp.services.profile_loader import load_user_profile

logger = logging.getLogger(__name__)

_SYMPTOM_ALLOW = frozenset({"dry", "oily", "dull", "breakout", "spots", "normal"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _filter_symptoms(keywords: list[str]) -> list[str]:
    return [k for k in keywords if k in _SYMPTOM_ALLOW and k != "normal"]


def _profile_dict(profile, *, city: str) -> dict[str, str]:
    concern = resolve_concern_id(profile=profile) or "acne"
    skin = profile.skin_type.value if hasattr(profile.skin_type, "value") else str(profile.skin_type)
    gender = profile.gender.value if hasattr(profile.gender, "value") else str(profile.gender)
    age = profile.age_bracket.value if hasattr(profile.age_bracket, "value") else str(profile.age_bracket)
    life = ""
    if profile.life_stage:
        life = profile.life_stage.value if hasattr(profile.life_stage, "value") else str(profile.life_stage)
    return {
        "city": city,
        "skin": skin,
        "concern": concern,
        "age": age,
        "life": life or gender,
    }


def _enrich_pattern_library(patterns: list[Pattern], profile: dict, ev_master: dict) -> None:
    """Attach scenario-library cell ids + PMIDs using band_bridge keys."""
    for p in patterns:
        band_key = None
        if p.chart:
            high_days = [c for c in p.chart if c.get("lvl", 0) >= 0.6]
            if high_days:
                band_key = "high"
        cell_key = scenario_master_key(
            p.driver,
            band_key or "high",
            profile.get("skin", "normal"),
            profile.get("concern", "acne"),
        )
        cell = ev_master.get(cell_key)
        if cell:
            p.library_cell_id = cell_key
            raw_pmids = list(cell.get("pmids") or cell.get("evidence") or [])[:3]
            p.pmids = [str(x).replace("PMID ", "").strip() for x in raw_pmids if x]


async def _load_daily_logs(user_id: str, today: date) -> list[DailyLog]:
    since = datetime.combine(today - timedelta(days=RETENTION_DAYS - 1), datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    event_docs = await fetch_log_events(user_id, since=since, limit=500)
    feelings_by_day = _latest_feelings_by_day_from_sessions(event_docs)
    daily_docs = await fetch_daily_logs(user_id, since=since, limit=RETENTION_DAYS)

    city_by_day: dict[str, str] = {}
    for doc in daily_docs:
        day = str(doc.get("date") or "")
        if day and doc.get("city"):
            city_by_day[day] = str(doc["city"])

    for doc in event_docs:
        day = str(doc.get("date") or "")
        if day and doc.get("city"):
            city_by_day.setdefault(day, str(doc["city"]))

    log_days = set(feelings_by_day.keys())
    for doc in daily_docs:
        if doc.get("user_logged"):
            log_days.add(str(doc.get("date") or ""))
    log_days.discard("")

    logs: list[DailyLog] = []
    for day_key in sorted(log_days):
        try:
            log_date = date.fromisoformat(day_key)
        except ValueError:
            continue
        syms = _filter_symptoms(feelings_by_day.get(day_key, []))
        zones: list[str] = []
        for doc in reversed(event_docs):
            if str(doc.get("date") or "") == day_key:
                zones = [str(z) for z in (doc.get("areas") or []) if z]
                break
        logs.append(
            DailyLog(
                user_id=user_id,
                log_date=log_date,
                city=city_by_day.get(day_key, ""),
                symptoms=syms,
                zones=zones,
            )
        )
    return logs


async def _build_env_map(user_id: str, today: date) -> dict[date, EnvDay]:
    since = datetime.combine(today - timedelta(days=RETENTION_DAYS - 1), datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    daily_docs = await fetch_daily_logs(user_id, since=since, limit=RETENTION_DAYS)
    env: dict[date, EnvDay] = {}
    for doc in daily_docs:
        day_key = str(doc.get("date") or "")
        if not day_key:
            continue
        try:
            d = date.fromisoformat(day_key)
        except ValueError:
            continue
        bands = daily_doc_band_keys(doc)
        env[d] = EnvDay(
            city=str(doc.get("city") or ""),
            day=d,
            band_keys={k: v for k, v in bands.items() if v},
        )
    return env


async def _resolve_first_log_date(user_id: str, ps: PatternState, logs: list[DailyLog]) -> date | None:
    if ps.first_log_date:
        return ps.first_log_date
    dates = await fetch_log_event_dates(user_id)
    if dates:
        first = min(date.fromisoformat(d) for d in dates)
        await set_first_log_date_if_missing(user_id, first)
        return first
    if logs:
        first = min(lg.log_date for lg in logs)
        await set_first_log_date_if_missing(user_id, first)
        return first
    return None


def _stability_partial(ps: PatternState) -> bool:
    if ps.unlocked_at is not None:
        return False
    if ps.state != "EARLY_SIGNALS":
        return False
    floor_ok = ps.first_log_date is not None
    if floor_ok:
        # consistency met in evaluate_state branch for calm month
        return ps.log_days_30 >= Config.UNLOCK_LOG_DAYS
    return False


async def recompute_patterns_for_user(
    user_id: str,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Run state machine + detection, persist, return v4 payload."""
    today = today or today_local()
    profile_model = await load_user_profile(user_id)
    if profile_model is None:
        return {
            "state": "LOCKED",
            "stability_partial": False,
            "meter": {
                "log_days": 0,
                "log_days_target": Config.UNLOCK_LOG_DAYS,
                "exposure_days": 0,
                "exposure_target": Config.EXPOSURE_MIN_DAYS,
                "days_since_first_log": 0,
                "floor_days": Config.UNLOCK_HARD_FLOOR_DAYS,
                "projected_unlock_date": None,
            },
            "freshness": None,
            "patterns": [],
            "emerging": [],
            "message": "Complete your skin profile first",
        }

    logs = await _load_daily_logs(user_id, today)
    env = await _build_env_map(user_id, today)
    ps = await get_pattern_state(user_id)
    ps.first_log_date = await _resolve_first_log_date(user_id, ps, logs)

    prev_unlocked = ps.unlocked_at is not None
    prev_state = ps.state
    prev_decay_notified = ps.last_decay_notified_state

    evaluate_state(ps, logs, env, today)

    from app.hlhp.services.patterns_lifecycle_service import (
        apply_state_transitions,
        notify_unlock,
    )

    await apply_state_transitions(
        user_id,
        prev_state=prev_state,
        ps=ps,
        prev_decay_notified=prev_decay_notified,
    )
    await save_pattern_state(ps)

    store = get_scenario_store()
    ev_master = store.master

    city = ""
    if logs:
        city = next((lg.city for lg in reversed(logs) if lg.city), "")
    profile = _profile_dict(profile_model, city=city)

    prev_patterns = await get_stored_patterns(user_id)
    patterns = detect_patterns(
        user_id,
        logs,
        env,
        profile,
        ev_master,
        today,
        prev_patterns=prev_patterns or None,
    )
    _enrich_pattern_library(patterns, profile, ev_master)

    # Attach zones from logs for narration/templates
    logs_by_day = {lg.log_date: lg for lg in logs}
    for p in patterns:
        if not p.zones:
            for d in logs_by_day:
                if p.symptom in logs_by_day[d].symptoms and logs_by_day[d].zones:
                    p.zones = list(logs_by_day[d].zones)[:3]
                    break

    await save_patterns(user_id, patterns)

    alerts = await get_pattern_alerts(user_id)
    stability = _stability_partial(ps)
    payload = build_patterns_payload(ps, patterns, logs, today, stability, alerts)

    if ps.state in ("LOCKED", "EARLY_SIGNALS"):
        from app.hlhp.services.patterns_generic_city import build_generic_city_pattern

        generic = build_generic_city_pattern(
            user_id=user_id,
            city=city or profile.get("city", ""),
            profile=profile_model,
        )
        if generic:
            payload["generic_city_pattern"] = generic

    # Fire unlock-side effects (narration refresh) when newly unlocked
    if not prev_unlocked and ps.unlocked_at is not None:
        from app.hlhp.patterns.hlhp_patterns_prompts import lifecycle
        from app.hlhp.services.patterns_lifecycle_service import notify_unlock
        from app.hlhp.services.patterns_narration_service import refresh_narration_on_unlock

        promoted_count = len([p for p in patterns if p.status == "promoted"])
        payload["unlock_celebration"] = {
            "headline": lifecycle("unlock.screen"),
            "stats": lifecycle("unlock.stats", log_days=ps.log_days_30, n=promoted_count),
            "log_days": ps.log_days_30,
            "pattern_count": promoted_count,
        }

        try:
            await notify_unlock(user_id)
        except Exception as exc:
            logger.warning("patterns unlock notify skipped user=%s: %s", user_id, exc)
        try:
            await refresh_narration_on_unlock(user_id, ps, patterns, profile)
        except Exception as exc:
            logger.warning("patterns unlock narration skipped user=%s: %s", user_id, exc)
    elif prev_state != ps.state:
        logger.info("patterns state change user=%s %s -> %s", user_id, prev_state, ps.state)

    payload["workbook_version"] = store.workbook_version

    try:
        from app.hlhp.services.patterns_nudge_service import run_nudges_for_user

        await run_nudges_for_user(user_id, today=today, patterns=patterns, profile=profile)
    except Exception as exc:
        logger.warning("patterns nudges skipped user=%s: %s", user_id, exc)

    try:
        from app.hlhp.services.patterns_alert_forecast import run_pattern_alert_forecast

        await run_pattern_alert_forecast(user_id, today=today)
    except Exception as exc:
        logger.warning("patterns forecast skipped user=%s: %s", user_id, exc)

    try:
        from app.hlhp.services.pattern_push_consumer import deliver_pending_notifications

        await deliver_pending_notifications(user_id=user_id, limit=10)
    except Exception as exc:
        logger.warning("pattern push drain skipped user=%s: %s", user_id, exc)

    return payload


async def assemble_patterns_state(user_id: str) -> dict[str, Any]:
    payload = await recompute_patterns_for_user(user_id)
    return {
        k: payload[k]
        for k in ("state", "meter", "freshness", "stability_partial", "reactivation")
        if k in payload
    }


async def toggle_pattern_alert(
    user_id: str,
    pattern_id: str,
    *,
    on: bool,
) -> dict[str, Any]:
    alerts = await get_pattern_alerts(user_id)
    if on:
        patterns = await get_stored_patterns(user_id)
        pat = next((p for p in patterns if f"{p.driver}:{p.symptom}" == pattern_id), None)
        if pat is None:
            return {"pattern_id": pattern_id, "subscribed": False, "error": "pattern_not_found"}
        subscribe_alert(user_id, pat, alerts)
    else:
        unsubscribe_alert(user_id, pattern_id, alerts)
    await save_pattern_alerts(user_id, alerts)
    return {
        "pattern_id": pattern_id,
        "subscribed": is_subscribed(user_id, pattern_id, alerts),
    }
