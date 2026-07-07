"""History lane + catch-up narrative assembly."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.coach.state_store import _load_user_name, fetch_daily_feeling_keywords
from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.history import (
    CatchupResponse,
    HistoryDayLog,
    HistoryFeelingSession,
    HistoryResponse,
    MostFiredMood,
    ReturnerBanner,
    SfiTrendPoint,
    SuddenEventEntry,
)
from app.hlhp.services.daily_log_store import (
    RETENTION_DAYS,
    average_daily_scores,
    backfill_from_scans,
    fetch_daily_logs,
)
from app.hlhp.services.log_event_store import fetch_log_events
from app.hlhp.services.scan_log_store import fetch_scans, scan_gap_days

_TRACKING_PROMPT = (
    "Visit SkinBB daily and open Today to keep your skin log going — "
    "we save up to 30 days of your scores and how you felt."
)

_SUDDEN_LABELS = {
    "humidity_surge": ("Humidity surge", "Pre-monsoon / muggy stretch — fungal-acne window"),
    "heat_surge": ("Heat wave surge", "Sebum-rush conditions · flare-prone"),
    "uv_surge": ("UV surge", "Pigment and tan pressure rises"),
    "transition_shock_day": ("Transition day", "Routine adjustment recommended"),
}


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _humanize_feeling(keyword: str) -> str:
    return keyword.replace("_", " ").strip().title()


def _day_description_from_doc(doc: dict[str, Any]) -> str:
    return _env_description_from_doc(doc)


def _env_description_from_doc(doc: dict[str, Any]) -> str:
    uvi = float(doc.get("uvi", 0))
    temp = float(doc.get("temp_c", 0))
    tags = doc.get("sudden_event_tags") or []
    env_line = f"{temp:.0f}°C outdoors · UV index {uvi:.0f}"
    if tags:
        tag = str(tags[0]).replace("_", " ").strip()
        return f"{tag.capitalize()}. {env_line}."
    return f"{env_line}."


def _normalize_symptoms(symptoms: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in symptoms:
        kw = str(raw).strip().lower().replace(" ", "_")
        if kw and kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out


def _latest_feelings_by_day_from_sessions(
    events: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Most recent committed session per calendar day -> symptom keywords."""
    latest: dict[str, tuple[datetime, list[str]]] = {}
    for doc in events:
        ts = doc.get("ts")
        if ts is None:
            continue
        when = _parse_dt(ts)
        date_key = str(doc.get("date") or when.date().isoformat())
        keywords = _normalize_symptoms(list(doc.get("symptoms") or []))
        if not keywords:
            continue
        prev = latest.get(date_key)
        if prev is None or when > prev[0]:
            latest[date_key] = (when, keywords)
    return {day: kws for day, (_, kws) in latest.items()}


def _feeling_sessions_from_events(
    events: list[dict[str, Any]],
    *,
    now: datetime,
) -> list[HistoryFeelingSession]:
    sessions: list[HistoryFeelingSession] = []
    for doc in sorted(events, key=lambda d: d.get("ts"), reverse=True):
        ts = doc.get("ts")
        if ts is None:
            continue
        when = _parse_dt(ts)
        symptoms = _normalize_symptoms(list(doc.get("symptoms") or []))
        if not symptoms:
            continue
        date_key = str(doc.get("date") or when.date().isoformat())
        days_ago = max(0, (now.date() - when.date()).days)
        sfi_val = doc.get("sfi")
        tags = doc.get("sudden_event_tags") or []
        sessions.append(
            HistoryFeelingSession(
                session_id=str(doc.get("session_id") or ""),
                committed_at=when.isoformat(),
                date=date_key,
                days_ago=days_ago,
                feelings=[_humanize_feeling(k) for k in symptoms],
                outdoor_score=int(sfi_val) if sfi_val is not None else None,
                mood_display=(
                    mood_headline(str(doc.get("mood_verdict") or ""))
                    if doc.get("mood_verdict")
                    else ""
                ),
                session_description=_env_description_from_doc(doc),
                sudden_event=bool(tags),
                driver=str(doc.get("driver") or "") or None,
            )
        )
    return sessions


def _sudden_entry(tag: str, scan_date: datetime, now: datetime) -> SuddenEventEntry:
    label, detail = _SUDDEN_LABELS.get(
        tag.replace(" ", "_"),
        (tag.replace("_", " ").title(), "Environmental shift detected"),
    )
    days_ago = max(0, (now.date() - scan_date.date()).days)
    return SuddenEventEntry(
        date=scan_date.date().isoformat(),
        days_ago=days_ago,
        tag=tag,
        headline=label,
        detail=detail,
    )


def _merge_feeling_only_docs(
    daily_docs: list[dict[str, Any]],
    feelings_by_day: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Include days where the user logged feelings but no scan aggregate exists yet."""
    by_date = {str(d.get("date") or ""): d for d in daily_docs if d.get("date")}
    for date_key, keywords in feelings_by_day.items():
        if date_key and date_key not in by_date and keywords:
            by_date[date_key] = {
                "date": date_key,
                "outdoor_score_avg": None,
                "user_logged": True,
            }
    return sorted(by_date.values(), key=lambda d: d.get("date", ""))


def _latest_session_doc_by_day(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for doc in events:
        ts = doc.get("ts")
        if ts is None:
            continue
        when = _parse_dt(ts)
        date_key = str(doc.get("date") or when.date().isoformat())
        prev = latest.get(date_key)
        if prev is None or when > prev[0]:
            latest[date_key] = (when, doc)
    return {day: doc for day, (_, doc) in latest.items()}


def _daily_logs_from_store(
    docs: list[dict[str, Any]],
    feelings_by_day: dict[str, list[str]],
    *,
    sessions_by_day: dict[str, dict[str, Any]],
    now: datetime,
) -> list[HistoryDayLog]:
    logs: list[HistoryDayLog] = []
    for doc in sorted(docs, key=lambda d: d.get("date", ""), reverse=True):
        date_key = str(doc.get("date") or "")
        if not date_key:
            continue
        try:
            day = datetime.strptime(date_key, "%Y-%m-%d").date()
            days_ago = max(0, (now.date() - day).days)
        except ValueError:
            days_ago = 0
        avg = doc.get("outdoor_score_avg")
        session_doc = sessions_by_day.get(date_key)
        session_sfi = session_doc.get("sfi") if session_doc else None
        if session_sfi is not None:
            outdoor_score = int(session_sfi)
        elif avg is not None:
            outdoor_score = int(round(float(avg)))
        else:
            outdoor_score = None
        if session_doc and ("uvi" in session_doc or "temp_c" in session_doc):
            day_description = _env_description_from_doc(session_doc)
        elif "uvi" in doc or "temp_c" in doc:
            day_description = _day_description_from_doc(doc)
        else:
            day_description = "Logged how your skin felt."
        mood_source = session_doc or doc
        logs.append(
            HistoryDayLog(
                date=date_key,
                days_ago=days_ago,
                outdoor_score=outdoor_score,
                mood_display=(
                    mood_headline(str(mood_source.get("mood_verdict") or ""))
                    if mood_source.get("mood_verdict")
                    else ""
                ),
                day_description=day_description,
                feelings=[_humanize_feeling(k) for k in feelings_by_day.get(date_key, [])],
                sudden_event=bool(
                    doc.get("sudden_event")
                    or (session_doc and session_doc.get("sudden_event_tags"))
                ),
                is_sample=False,
                logged=bool(doc.get("user_logged") or feelings_by_day.get(date_key)),
            )
        )
    return logs


async def assemble_history(user_id: str, *, days: int = RETENTION_DAYS) -> HistoryResponse:
    store = get_scenario_store()
    now = datetime.now(timezone.utc)
    span = min(max(1, days), RETENTION_DAYS)
    since = now - timedelta(days=span)
    scans = await fetch_scans(user_id, since=since)
    feelings_by_day = await fetch_daily_feeling_keywords(user_id, since=since)
    log_events = await fetch_log_events(user_id, since=since)
    feeling_sessions = _feeling_sessions_from_events(log_events, now=now)
    session_feelings_by_day = _latest_feelings_by_day_from_sessions(log_events)
    sessions_by_day = _latest_session_doc_by_day(log_events)
    for date_key, keywords in session_feelings_by_day.items():
        feelings_by_day[date_key] = keywords

    daily_docs = await fetch_daily_logs(user_id, since=since, limit=span)
    if not daily_docs and scans:
        await backfill_from_scans(user_id, scans)
        daily_docs = await fetch_daily_logs(user_id, since=since, limit=span)

    daily_docs = _merge_feeling_only_docs(daily_docs, feelings_by_day)

    daily_logs = _daily_logs_from_store(
        daily_docs,
        feelings_by_day,
        sessions_by_day=sessions_by_day,
        now=now,
    )
    daily_by_date = {str(d.get("date") or ""): d for d in daily_docs if d.get("date")}
    scan_count = sum(int(d.get("scan_count") or 0) for d in daily_docs)
    logged_days = len(daily_logs)
    sfi_avg = average_daily_scores(daily_docs)

    if not daily_logs and not feeling_sessions:
        return HistoryResponse(
            user_id=user_id,
            days=span,
            scan_count=0,
            is_demo=False,
            sfi_average=None,
            sudden_events=[],
            daily_logs=[],
            feeling_sessions=[],
            message="No daily logs yet — open Today to start your 30-day skin track.",
            tracking_prompt=_TRACKING_PROMPT,
            show_tracking_prompt=True,
            workbook_version=store.workbook_version,
        )

    prior_since = since - timedelta(days=span)
    prior_docs = await fetch_daily_logs(user_id, since=prior_since, limit=span)
    prior_docs = [d for d in prior_docs if str(d.get("date", "")) < since.date().isoformat()]
    sfi_prior = average_daily_scores(prior_docs)
    sfi_delta = None
    if sfi_avg is not None and sfi_prior is not None:
        sfi_delta = round(sfi_avg - sfi_prior, 1)

    trend: list[SfiTrendPoint] = []
    sudden_events: list[SuddenEventEntry] = []
    seen_sudden_dates: set[str] = set()

    for i in range(span - 1, -1, -1):
        date_key = (now.date() - timedelta(days=i)).isoformat()
        doc = daily_by_date.get(date_key, {})
        avg = doc.get("outdoor_score_avg")
        has_feelings = bool(feelings_by_day.get(date_key))
        has_score = avg is not None
        if not has_score and not has_feelings:
            trend.append(
                SfiTrendPoint(
                    date=date_key,
                    sfi=None,
                    driver=None,
                    feeling_logged=False,
                )
            )
            continue

        trend.append(
            SfiTrendPoint(
                date=date_key,
                sfi=int(round(float(avg))) if has_score else None,
                sudden_event=bool(doc.get("sudden_event")),
                driver=str(doc.get("driver") or "") or None if has_score else None,
                feeling_logged=has_feelings and not has_score,
            )
        )

    for doc in sorted(daily_docs, key=lambda d: d.get("date", "")):
        date_key = str(doc.get("date") or "")
        if not date_key:
            continue
        tags = doc.get("sudden_event_tags") or []
        if tags and date_key not in seen_sudden_dates:
            seen_sudden_dates.add(date_key)
            try:
                day_dt = datetime.strptime(date_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                day_dt = now
            sudden_events.append(_sudden_entry(str(tags[0]), day_dt, now))

    sudden_events.sort(key=lambda e: e.date, reverse=True)
    sudden_events = sudden_events[:5]

    mood_counts: Counter[str] = Counter()
    for doc in daily_docs:
        mood = str(doc.get("mood_verdict") or "").strip()
        if mood:
            mood_counts[mood] += 1

    most_fired: Optional[MostFiredMood] = None
    if mood_counts:
        top_mood, count = mood_counts.most_common(1)[0]
        most_fired = MostFiredMood(
            mood=top_mood,
            display=mood_headline(top_mood),
            days_count=count,
        )

    returner: Optional[ReturnerBanner] = None
    gap = await scan_gap_days(user_id)
    if gap is not None and gap >= 14:
        name = ""
        try:
            name = await _load_user_name(user_id)
        except Exception:
            name = ""
        city = str(
            (daily_docs[0].get("city") if daily_docs else None)
            or (scans[-1].get("city") if scans else None)
            or "your city"
        )
        greeting = f"Welcome back{', ' + name if name else ''}."
        returner = ReturnerBanner(
            show=True,
            days_away=gap,
            headline=greeting,
            context=(
                f"While you were away, {city} had shifting humidity and UV — "
                f"your skin probably noticed. Here is what we saved from the last {span} days."
            ),
        )

    show_prompt = logged_days < span
    message = None
    if logged_days < span:
        message = (
            f"{logged_days} of {span} days logged — open Today each day to build a complete "
            "30-day skin track."
        )

    return HistoryResponse(
        user_id=user_id,
        days=span,
        scan_count=scan_count or logged_days,
        is_demo=False,
        sfi_average=sfi_avg,
        sfi_prior_period_average=sfi_prior,
        sfi_delta_vs_prior=sfi_delta,
        sudden_events=sudden_events,
        daily_logs=daily_logs,
        feeling_sessions=feeling_sessions,
        trend=trend,
        most_fired_mood=most_fired,
        returner_banner=returner,
        message=message,
        tracking_prompt=_TRACKING_PROMPT,
        show_tracking_prompt=show_prompt,
        workbook_version=store.workbook_version,
    )


async def assemble_catchup(user_id: str, *, days: int = RETENTION_DAYS) -> CatchupResponse:
    history = await assemble_history(user_id, days=days)
    store = get_scenario_store()
    now = datetime.now(timezone.utc)
    name = ""
    try:
        name = await _load_user_name(user_id)
    except Exception:
        name = ""
    paragraphs: list[str] = []

    if history.scan_count == 0:
        paragraphs = [
            "Your HLHP history starts with today's scan.",
            _TRACKING_PROMPT,
        ]
    else:
        lead = f"{name}, here is your catch-up." if name else "Here is your catch-up."
        paragraphs.append(lead)

        if history.sfi_average is not None:
            band = "manageable" if history.sfi_average >= 50 else "demanding"
            paragraphs.append(
                f"Over the last {history.days} days your skin-friendliness averaged "
                f"{history.sfi_average}/100 — mostly {band} outdoor days."
            )
            if history.sfi_delta_vs_prior is not None:
                direction = "up" if history.sfi_delta_vs_prior > 0 else "down"
                paragraphs.append(
                    f"That is {abs(history.sfi_delta_vs_prior):.0f} points {direction} "
                    "compared with the prior period."
                )

        if history.sudden_events:
            evt = history.sudden_events[0]
            paragraphs.append(
                f"The biggest shift was {evt.headline.lower()} ({evt.days_ago} days ago). "
                f"{evt.detail}."
            )

        if history.most_fired_mood:
            paragraphs.append(
                f"Your most common day-type was {history.most_fired_mood.display.lower()} "
                f"({history.most_fired_mood.days_count} logged days)."
            )

        paragraphs.append(
            "Open Today daily so your 30-day log stays complete — scores and how you felt add up over time."
        )

    return CatchupResponse(
        user_id=user_id,
        paragraphs=paragraphs[:4],
        generated_at=now.isoformat(),
        workbook_version=store.workbook_version,
    )
