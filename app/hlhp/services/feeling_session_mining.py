"""Session-level feeling-log mining helpers (used by tests and unlock copy)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from app.hlhp.core.local_date import today_local

PATTERNS_UNLOCK_DAYS = 30
MIN_LOGS_TO_MINE = 25
PATTERNS_WINDOW_DAYS = 30
MIN_SYMPTOM_SESSIONS = 3
MIN_CO_SESSIONS = 3
MIN_MATCH_PCT = 60
MIN_LIFT = 1.25


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
