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
from app.hlhp.services.scan_log_store import fetch_scans, scan_gap_days

MIN_REAL_HISTORY_SCANS = 7
_DEMO_LOG_DAYS = 7

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


def _day_description(scan: dict[str, Any]) -> str:
    uvi = float(scan.get("uvi", 0))
    temp = float(scan.get("temp_c", 0))
    tags = scan.get("sudden_event_tags") or []
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


def _avg_sfi(scans: list[dict]) -> Optional[float]:
    scores = [int(s.get("outdoor_ok_score", 0)) for s in scans if s.get("outdoor_ok_score") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def _last_scan_per_day(scans: list[dict]) -> dict[str, dict]:
    by_day: dict[str, dict] = {}
    for scan in scans:
        scanned_at = _parse_dt(scan.get("scanned_at"))
        by_day[scanned_at.date().isoformat()] = scan
    return by_day


def _build_daily_logs(
    scans: list[dict],
    feelings_by_day: dict[str, list[str]],
    *,
    now: datetime,
) -> list[HistoryDayLog]:
    by_day = _last_scan_per_day(scans)
    logs: list[HistoryDayLog] = []
    for date_key in sorted(by_day.keys(), reverse=True):
        scan = by_day[date_key]
        scanned_at = _parse_dt(scan.get("scanned_at"))
        tags = scan.get("sudden_event_tags") or []
        logs.append(
            HistoryDayLog(
                date=date_key,
                days_ago=max(0, (now.date() - scanned_at.date()).days),
                outdoor_score=int(scan.get("outdoor_ok_score", 0)),
                mood_display=mood_headline(str(scan.get("mood_verdict") or "")),
                day_description=_day_description(scan),
                feelings=[_humanize_feeling(k) for k in feelings_by_day.get(date_key, [])],
                sudden_event=bool(tags),
            )
        )
    return logs


def _fill_recent_day_gaps(
    logs: list[HistoryDayLog],
    *,
    now: datetime,
    span_days: int = 7,
) -> list[HistoryDayLog]:
    """Show each recent calendar day — missing days appear as not logged."""
    by_date = {log.date: log for log in logs}
    filled: list[HistoryDayLog] = []
    for offset in range(span_days):
        day = now.date() - timedelta(days=offset)
        key = day.isoformat()
        if key in by_date:
            filled.append(by_date[key])
            continue
        filled.append(
            HistoryDayLog(
                date=key,
                days_ago=offset,
                outdoor_score=None,
                mood_display="No scan logged",
                day_description="Open Today to record how your skin felt that day.",
                feelings=[],
                logged=False,
            )
        )
    return filled


def _demo_daily_logs(now: datetime) -> list[HistoryDayLog]:
    """Sample week for History UI until enough real scans are logged."""
    samples = [
        (0, 52, "sebum_rush_day", "Heat plus muggy air — mid-day blot and evening cleanse help.", ["Oily", "Shiny"], True),
        (1, 58, "manageable_day", "Comfortable with sunscreen — routine basics carry the day.", ["Tight"], False),
        (2, 44, "pigment_overdrive_day", "High UV — tinted sunscreen and antioxidant serum matter.", ["Tan", "Dark spots"], True),
        (3, 61, "comfortable_day", "Balanced air — light moisturiser is enough.", [], False),
        (4, 38, "barrier_stress_day", "Dry air plus heat — barrier support and hydration help.", ["Tight", "Dry", "Flaky"], False),
        (5, 55, "sebum_rush_day", "Warm afternoon — jawline shine by mid-day.", ["Oily", "Congested"], False),
        (6, 63, "easy_day", "Easy outdoor day — SPF still earns its place.", [], False),
    ]
    logs: list[HistoryDayLog] = []
    for days_ago, score, mood, desc, feelings, sudden in samples:
        day = (now - timedelta(days=days_ago)).date()
        logs.append(
            HistoryDayLog(
                date=day.isoformat(),
                days_ago=days_ago,
                outdoor_score=score,
                mood_display=mood_headline(mood),
                day_description=desc,
                feelings=feelings,
                sudden_event=sudden,
                is_sample=True,
            )
        )
    return logs


def _demo_sudden_events(now: datetime) -> list[SuddenEventEntry]:
    return [
        SuddenEventEntry(
            date=(now - timedelta(days=2)).date().isoformat(),
            days_ago=2,
            tag="humidity_surge",
            headline="Humidity surge",
            detail="Pre-monsoon / muggy stretch — fungal-acne window",
        ),
        SuddenEventEntry(
            date=(now - timedelta(days=0)).date().isoformat(),
            days_ago=0,
            tag="heat_surge",
            headline="Heat wave surge",
            detail="Sebum-rush conditions · flare-prone",
        ),
    ]


async def assemble_history(user_id: str, *, days: int = 30) -> HistoryResponse:
    store = get_evidence_store()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    scans = await fetch_scans(user_id, since=since)
    feelings_by_day = await fetch_daily_feeling_keywords(user_id, since=since)

    if not scans:
        demo_logs = _demo_daily_logs(now)
        return HistoryResponse(
            user_id=user_id,
            days=days,
            scan_count=0,
            is_demo=True,
            sfi_average=round(sum(d.outdoor_score for d in demo_logs) / len(demo_logs), 1),
            sudden_events=_demo_sudden_events(now),
            daily_logs=demo_logs,
            message="Sample week below — your real log starts after daily scans.",
            workbook_version=store.workbook_version,
        )

    use_demo = len(scans) < MIN_REAL_HISTORY_SCANS

    prior_since = since - timedelta(days=days)
    prior_scans = await fetch_scans(user_id, since=prior_since)
    prior_scans = [s for s in prior_scans if _parse_dt(s.get("scanned_at")) < since]

    sfi_avg = _avg_sfi(scans)
    sfi_prior = _avg_sfi(prior_scans)
    sfi_delta = None
    if sfi_avg is not None and sfi_prior is not None:
        sfi_delta = round(sfi_avg - sfi_prior, 1)

    trend: list[SfiTrendPoint] = []
    sudden_events: list[SuddenEventEntry] = []
    seen_sudden_dates: set[str] = set()

    for scan in scans:
        scanned_at = _parse_dt(scan.get("scanned_at"))
        date_key = scanned_at.date().isoformat()
        tags = scan.get("sudden_event_tags") or []
        trend.append(
            SfiTrendPoint(
                date=date_key,
                sfi=int(scan.get("outdoor_ok_score", 0)),
                sudden_event=bool(tags),
            )
        )
        if tags and date_key not in seen_sudden_dates:
            seen_sudden_dates.add(date_key)
            sudden_events.append(_sudden_entry(str(tags[0]), scanned_at, now))

    sudden_events.sort(key=lambda e: e.date, reverse=True)
    sudden_events = sudden_events[:5]

    daily_logs = _build_daily_logs(scans, feelings_by_day, now=now)
    daily_logs = _fill_recent_day_gaps(daily_logs, now=now, span_days=_DEMO_LOG_DAYS)

    mood_counts: Counter[str] = Counter()
    for scan in scans:
        mood = str(scan.get("mood_verdict") or "").strip()
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
        city = scans[-1].get("city") or "your city"
        greeting = f"Welcome back{', ' + name if name else ''}."
        returner = ReturnerBanner(
            show=True,
            days_away=gap,
            headline=greeting,
            context=(
                f"While you were away, {city} had shifting humidity and UV — "
                "your skin probably noticed. Catching you up on the last 30 days."
            ),
        )

    message = None
    if use_demo:
        message = (
            f"{len(scans)} day(s) logged so far — open Today daily to fill the rest of your week."
        )

    display_sfi = sfi_avg
    display_sudden = sudden_events
    if use_demo and not sudden_events:
        display_sudden = _demo_sudden_events(now)
    if use_demo and sfi_avg is None:
        display_sfi = round(
            sum(d.outdoor_score for d in daily_logs[:_DEMO_LOG_DAYS]) / min(len(daily_logs), _DEMO_LOG_DAYS),
            1,
        )

    return HistoryResponse(
        user_id=user_id,
        days=days,
        scan_count=len(scans),
        is_demo=use_demo,
        sfi_average=display_sfi,
        sfi_prior_period_average=sfi_prior,
        sfi_delta_vs_prior=sfi_delta,
        sudden_events=display_sudden,
        daily_logs=daily_logs,
        trend=trend,
        most_fired_mood=most_fired,
        returner_banner=returner,
        message=message,
        workbook_version=store.workbook_version,
    )


async def assemble_catchup(user_id: str, *, days: int = 30) -> CatchupResponse:
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
            "Open the Today lane daily and this catch-up will summarise patterns for you.",
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
                    "compared with the prior month."
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
                f"({history.most_fired_mood.days_count} of {history.scan_count} scans)."
            )

        paragraphs.append(
            "This week: hold sunscreen through mid-day, gentle cleanse at night, "
            "and tap a symptom chip if something feels off — the explainer is instant."
        )

    return CatchupResponse(
        user_id=user_id,
        paragraphs=paragraphs[:4],
        generated_at=now.isoformat(),
        workbook_version=store.workbook_version,
    )
