"""Mine symptom–environment patterns from committed feeling sessions (rule-based statistics)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from datetime import date

from app.hlhp.core.local_date import today_local
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.patterns import PatternInsight, PatternsResponse
from app.hlhp.services.daily_log_store import RETENTION_DAYS
from app.hlhp.services.log_event_store import fetch_log_event_dates, fetch_log_events

logger = logging.getLogger(__name__)

PATTERNS_UNLOCK_DAYS = 30
MIN_LOGS_TO_MINE = 25
PATTERNS_WINDOW_DAYS = 30
MIN_SYMPTOM_SESSIONS = 3
MIN_CO_SESSIONS = 3
MIN_MATCH_PCT = 60
MIN_LIFT = 1.25
MAX_PATTERNS = 2

_CTA_BY_DRIVER: dict[str, tuple[str, str]] = {
    "humidity_high": ("See humid-day tips", "humidity_surge"),
    "humidity_surge": ("See humid-day tips", "humidity_surge"),
    "heat_surge": ("See heat-surge tips", "heat_surge"),
    "uv_surge": ("See UV-surge tips", "uv_surge"),
    "pollution_surge": ("See air-quality tips", "pollution_surge"),
    "uv_high": ("See UV-shield tips", "shield"),
    "aqi_poor": ("See air-quality tips", "shield"),
    "hot_day": ("See heat-day tips", "heat_surge"),
    "low_sfi": ("See tough-day tips", "shield"),
}

_DRIVER_SHORT: dict[str, str] = {
    "humidity_surge": "humidity surge",
    "heat_surge": "heat surge",
    "uv_surge": "UV surge",
    "pollution_surge": "poor-air spikes",
    "humidity_high": "high humidity",
    "uv_high": "high UV",
    "aqi_poor": "poor air quality",
    "hot_day": "hot outdoor conditions",
    "low_sfi": "low skin-friendliness",
}


def _humanize(keyword: str) -> str:
    return keyword.replace("_", " ").strip().title()


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


@dataclass
class SessionRecord:
    session_id: str
    ts: datetime
    date: str
    feelings: set[str] = field(default_factory=set)
    rh_pct: Optional[float] = None
    uvi: Optional[float] = None
    aqi: Optional[int] = None
    temp_c: Optional[float] = None
    sfi: Optional[int] = None
    sudden_tags: set[str] = field(default_factory=set)
    weekday: int = 0


@dataclass(frozen=True)
class DriverRule:
    key: str
    label: str
    test: Callable[[SessionRecord], bool]


def _driver_rules() -> list[DriverRule]:
    return [
        DriverRule(
            "humidity_surge",
            "humidity surge",
            lambda s: "humidity_surge" in s.sudden_tags,
        ),
        DriverRule(
            "heat_surge",
            "heat surge",
            lambda s: "heat_surge" in s.sudden_tags,
        ),
        DriverRule(
            "uv_surge",
            "UV surge",
            lambda s: "uv_surge" in s.sudden_tags,
        ),
        DriverRule(
            "pollution_surge",
            "pollution spike",
            lambda s: "pollution_surge" in s.sudden_tags,
        ),
        DriverRule(
            "humidity_high",
            "high humidity (RH above 75%)",
            lambda s: s.rh_pct is not None and s.rh_pct > 75,
        ),
        DriverRule(
            "uv_high",
            "high UV (index 8 or above)",
            lambda s: s.uvi is not None and s.uvi >= 8,
        ),
        DriverRule(
            "aqi_poor",
            "poor air quality (AQI above 100)",
            lambda s: s.aqi is not None and s.aqi > 100,
        ),
        DriverRule(
            "hot_day",
            "hot outdoor conditions (32°C or above)",
            lambda s: s.temp_c is not None and s.temp_c >= 32,
        ),
        DriverRule(
            "low_sfi",
            "low skin-friendliness (SFI below 50)",
            lambda s: s.sfi is not None and s.sfi < 50,
        ),
    ]


def _session_from_event(doc: dict[str, Any]) -> SessionRecord | None:
    ts = doc.get("ts")
    if ts is None:
        return None
    when = _parse_dt(ts)
    date_key = str(doc.get("date") or when.date().isoformat())
    try:
        wd = datetime.strptime(date_key, "%Y-%m-%d").date().weekday()
    except ValueError:
        wd = when.weekday()
    feelings = {
        str(kw).strip().lower().replace(" ", "_")
        for kw in (doc.get("symptoms") or [])
        if str(kw).strip()
    }
    if not feelings:
        return None
    sfi_val = doc.get("sfi")
    return SessionRecord(
        session_id=str(doc.get("session_id") or ""),
        ts=when,
        date=date_key,
        feelings=feelings,
        rh_pct=float(doc["rh_pct"]) if doc.get("rh_pct") is not None else None,
        uvi=float(doc["uvi"]) if doc.get("uvi") is not None else None,
        aqi=int(doc["aqi"]) if doc.get("aqi") is not None else None,
        temp_c=float(doc["temp_c"]) if doc.get("temp_c") is not None else None,
        sfi=int(sfi_val) if sfi_val is not None else None,
        sudden_tags={str(t) for t in (doc.get("sudden_event_tags") or []) if t},
        weekday=wd,
    )


def _sessions_from_events(docs: list[dict[str, Any]]) -> list[SessionRecord]:
    out: list[SessionRecord] = []
    for doc in docs:
        rec = _session_from_event(doc)
        if rec is not None:
            out.append(rec)
    return out


def _calendar_days(span_days: int, now: datetime) -> list[str]:
    end = now.date()
    start = end - timedelta(days=span_days - 1)
    days: list[str] = []
    cursor = start
    while cursor <= end:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def _symptom_sessions(sessions: list[SessionRecord], symptom: str) -> list[SessionRecord]:
    return [s for s in sessions if symptom in s.feelings]


def _evaluate(
    sessions: list[SessionRecord],
    symptom: str,
    rule: DriverRule,
) -> Optional[dict[str, Any]]:
    symptom_sessions = _symptom_sessions(sessions, symptom)
    n_symptom = len(symptom_sessions)
    if n_symptom < MIN_SYMPTOM_SESSIONS:
        return None

    n_sessions = len(sessions)
    n_driver_all = sum(1 for s in sessions if rule.test(s))
    n_both = sum(1 for s in symptom_sessions if rule.test(s))

    if n_both == 0:
        return None

    p_given_symptom = n_both / n_symptom
    baseline = n_driver_all / n_sessions if n_sessions else 0
    match_pct = round(100 * p_given_symptom)
    baseline_pct = round(100 * baseline)

    if match_pct < MIN_MATCH_PCT:
        return None
    if n_both < MIN_CO_SESSIONS:
        return None
    if baseline > 0 and p_given_symptom / baseline < MIN_LIFT:
        return None

    lift = p_given_symptom / baseline if baseline > 0 else p_given_symptom
    score = match_pct * min(n_both, 12) * min(lift, 4.0)

    return {
        "symptom": symptom,
        "rule": rule,
        "n_both": n_both,
        "n_symptom": n_symptom,
        "match_pct": min(99, match_pct),
        "baseline_pct": baseline_pct,
        "score": score,
    }


def _timeline_series(
    calendar: list[str],
    sessions: list[SessionRecord],
    symptom: str,
    rule: DriverRule,
) -> list[int]:
    by_date: dict[str, list[SessionRecord]] = {}
    for session in sessions:
        by_date.setdefault(session.date, []).append(session)

    series: list[int] = []
    for day in calendar:
        day_sessions = by_date.get(day, [])
        has_symptom = any(symptom in s.feelings for s in day_sessions)
        has_both = any(symptom in s.feelings and rule.test(s) for s in day_sessions)
        if has_both:
            series.append(2)
        elif has_symptom:
            series.append(1)
        else:
            series.append(0)
    return series


def _title(symptom: str, rule: DriverRule) -> str:
    sym = _humanize(symptom)
    driver = _DRIVER_SHORT.get(rule.key, rule.label)
    return f"{sym} on {driver}"


def _body(symptom: str, rule: DriverRule, *, n_both: int, n_symptom: int) -> str:
    sym = _humanize(symptom).lower()
    driver = _DRIVER_SHORT.get(rule.key, rule.label)
    if n_both >= n_symptom:
        return f"All {n_symptom} times you logged {sym} lined up with {driver}."
    return f"{n_both} of {n_symptom} {sym} logs lined up with {driver}."


def _days_between_inclusive(start_iso: str, end_iso: str) -> int:
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    return (end - start).days + 1


def _journey_day(all_log_dates: set[str], *, today_iso: str | None = None) -> int:
    if not all_log_dates:
        return 0
    first = min(all_log_dates)
    end = today_iso or today_local().isoformat()
    return _days_between_inclusive(first, end)


def _pattern_unlock_copy(
    journey_day: int,
    *,
    unlock_days: int = PATTERNS_UNLOCK_DAYS,
) -> tuple[bool, int, str, str]:
    """Unlock the Patterns tab after enough days on track from the first feeling log."""
    days_needed = max(0, unlock_days - journey_day)
    ready = days_needed == 0
    if ready:
        return True, 0, "Patterns unlocked", ""
    day_word = "day" if days_needed == 1 else "days"
    headline = f"Patterns unlock after {unlock_days} days on your track"
    detail = (
        f"You're on day {journey_day} of your track — "
        f"{days_needed} more {day_word} to go."
    )
    return False, days_needed, headline, detail


def _mining_gate_copy(
    logged_days: int,
    *,
    min_logs: int = MIN_LOGS_TO_MINE,
    window_days: int = PATTERNS_WINDOW_DAYS,
) -> tuple[bool, int, str]:
    """Mine relevant patterns only after enough distinct feeling-log days in the window."""
    logs_needed = max(0, min_logs - logged_days)
    can_mine = logs_needed == 0
    if can_mine:
        return True, 0, ""
    day_word = "day" if logs_needed == 1 else "days"
    message = (
        f"Log feelings on at least {min_logs} days in your last {window_days} days "
        f"for personalized patterns — you have {logged_days} of {min_logs} "
        f"({logs_needed} more log {day_word} to go)."
    )
    return False, logs_needed, message


async def assemble_patterns(user_id: str, *, days: int = RETENTION_DAYS) -> PatternsResponse:
    store = get_scenario_store()
    now = datetime.now(timezone.utc)
    span = min(max(1, days), RETENTION_DAYS)
    since = now - timedelta(days=span)

    all_log_dates = await fetch_log_event_dates(user_id)
    journey_day = _journey_day(all_log_dates)

    event_docs = await fetch_log_events(user_id, since=since)
    sessions = _sessions_from_events(event_docs)
    calendar = _calendar_days(span, now)

    logged_days = len({s.date for s in sessions})
    all_symptoms: set[str] = set()
    for session in sessions:
        all_symptoms.update(session.feelings)

    ready, logs_needed, unlock_headline, unlock_detail = _pattern_unlock_copy(journey_day)
    can_mine, mining_logs_needed, mining_message = _mining_gate_copy(
        logged_days, window_days=span
    )

    if not ready:
        return PatternsResponse(
            user_id=user_id,
            days=span,
            window_days=span,
            journey_day=journey_day,
            log_count=logged_days,
            min_logs_required=PATTERNS_UNLOCK_DAYS,
            min_logs_to_mine=MIN_LOGS_TO_MINE,
            ready=False,
            can_mine=False,
            logs_needed=logs_needed,
            mining_logs_needed=mining_logs_needed,
            unlock_headline=unlock_headline,
            unlock_detail=unlock_detail,
            patterns=[],
            message=(
                f"Patterns unlock after {PATTERNS_UNLOCK_DAYS} days on your track. "
                "Keep logging daily to build your month."
            ),
            workbook_version=store.workbook_version,
        )

    if not can_mine:
        return PatternsResponse(
            user_id=user_id,
            days=span,
            window_days=span,
            journey_day=journey_day,
            log_count=logged_days,
            min_logs_required=PATTERNS_UNLOCK_DAYS,
            min_logs_to_mine=MIN_LOGS_TO_MINE,
            ready=True,
            can_mine=False,
            logs_needed=0,
            mining_logs_needed=mining_logs_needed,
            unlock_headline="Patterns unlocked",
            unlock_detail=None,
            patterns=[],
            message=mining_message,
            workbook_version=store.workbook_version,
        )

    candidates: list[dict[str, Any]] = []
    rules = _driver_rules()

    for symptom in sorted(all_symptoms):
        for rule in rules:
            hit = _evaluate(sessions, symptom, rule)
            if hit:
                candidates.append(hit)

    candidates.sort(key=lambda c: c["score"], reverse=True)
    seen_symptoms: set[str] = set()
    seen_drivers: set[str] = set()
    patterns: list[PatternInsight] = []

    for hit in candidates:
        if len(patterns) >= MAX_PATTERNS:
            break
        symptom = hit["symptom"]
        rule: DriverRule = hit["rule"]
        if symptom in seen_symptoms or rule.key in seen_drivers:
            continue
        chart = "timeline"
        cta_label, cta_tag = _CTA_BY_DRIVER.get(rule.key, ("Learn more", "shield"))

        patterns.append(
            PatternInsight(
                id=f"{symptom}_{rule.key}",
                symptom_keyword=symptom,
                driver=rule.key,
                title=_title(symptom, rule),
                body=_body(symptom, rule, n_both=hit["n_both"], n_symptom=hit["n_symptom"]),
                match_pct=hit["match_pct"],
                n=hit["n_both"],
                n_symptom_days=hit["n_symptom"],
                baseline_pct=hit["baseline_pct"],
                chart=chart,  # type: ignore[arg-type]
                timeline=_timeline_series(calendar, sessions, symptom, rule),
                weekgrid=[],
                hours=[],
                cta_label=cta_label,
                cta_tag=cta_tag,
            )
        )
        seen_symptoms.add(symptom)
        seen_drivers.add(rule.key)

    message = None
    if not patterns:
        message = (
            "No clear weather link yet. Keep logging on different days — "
            "humid, hot, and high-UV stretches help us spot what moves your skin."
        )

    return PatternsResponse(
        user_id=user_id,
        days=span,
        window_days=span,
        journey_day=journey_day,
        log_count=logged_days,
        min_logs_required=PATTERNS_UNLOCK_DAYS,
        min_logs_to_mine=MIN_LOGS_TO_MINE,
        ready=True,
        can_mine=True,
        logs_needed=0,
        mining_logs_needed=0,
        unlock_headline="Patterns unlocked",
        unlock_detail=None,
        patterns=patterns,
        message=message,
        workbook_version=store.workbook_version,
    )
