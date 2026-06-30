"""History lane + catch-up narrative assembly."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.coach.state_store import _load_user_name, fetch_daily_feeling_keywords
from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.history import (
    CatchupResponse,
    HistoryDayLog,
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
    uvi = float(doc.get("uvi", 0))
    temp = float(doc.get("temp_c", 0))
    tags = doc.get("sudden_event_tags") or []
    env_line = f"{temp:.0f}°C outdoors · UV index {uvi:.0f}"
    if tags:
        tag = str(tags[0]).replace("_", " ").strip()
        return f"{tag.capitalize()}. {env_line}."
    return f"{env_line}."


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


def _daily_logs_from_store(
    docs: list[dict[str, Any]],
    feelings_by_day: dict[str, list[str]],
    *,
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
        logs.append(
            HistoryDayLog(
                date=date_key,
                days_ago=days_ago,
                outdoor_score=int(round(float(avg))) if avg is not None else None,
                mood_display=(
                    mood_headline(str(doc.get("mood_verdict") or ""))
                    if doc.get("mood_verdict")
                    else ""
                ),
                day_description=(
                    _day_description_from_doc(doc)
                    if "uvi" in doc or "temp_c" in doc
                    else "Logged how your skin felt."
                ),
                feelings=[_humanize_feeling(k) for k in feelings_by_day.get(date_key, [])],
                sudden_event=bool(doc.get("sudden_event")),
                is_sample=False,
                logged=bool(doc.get("user_logged") or feelings_by_day.get(date_key)),
            )
        )
    return logs


async def assemble_history(user_id: str, *, days: int = RETENTION_DAYS) -> HistoryResponse:
    store = get_evidence_store()
    now = datetime.now(timezone.utc)
    span = min(max(1, days), RETENTION_DAYS)
    since = now - timedelta(days=span)
    scans = await fetch_scans(user_id, since=since)
    feelings_by_day = await fetch_daily_feeling_keywords(user_id, since=since)

    daily_docs = await fetch_daily_logs(user_id, since=since, limit=span)
    if not daily_docs and scans:
        await backfill_from_scans(user_id, scans)
        daily_docs = await fetch_daily_logs(user_id, since=since, limit=span)

    daily_docs = _merge_feeling_only_docs(daily_docs, feelings_by_day)

    daily_logs = _daily_logs_from_store(daily_docs, feelings_by_day, now=now)
    scan_count = sum(int(d.get("scan_count") or 0) for d in daily_docs)
    logged_days = len(daily_logs)
    sfi_avg = average_daily_scores(daily_docs)

    if not daily_logs:
        return HistoryResponse(
            user_id=user_id,
            days=span,
            scan_count=0,
            is_demo=False,
            sfi_average=None,
            sudden_events=[],
            daily_logs=[],
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

    for doc in sorted(daily_docs, key=lambda d: d.get("date", "")):
        date_key = str(doc.get("date") or "")
        if not date_key:
            continue
        avg = doc.get("outdoor_score_avg")
        has_feelings = bool(feelings_by_day.get(date_key))
        if avg is None and not has_feelings:
            continue
        trend.append(
            SfiTrendPoint(
                date=date_key,
                sfi=int(round(float(avg))) if avg is not None else 0,
                sudden_event=bool(doc.get("sudden_event")),
                driver=str(doc.get("driver") or "") or None,
            )
        )
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
    store = get_evidence_store()
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
