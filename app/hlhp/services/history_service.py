"""History lane + catch-up narrative assembly."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.hlhp.composition.vocabulary import mood_headline
from app.hlhp.coach.state_store import _load_user_name
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.history import (
    CatchupResponse,
    HistoryResponse,
    MostFiredMood,
    ReturnerBanner,
    SfiTrendPoint,
    SuddenEventEntry,
)
from app.hlhp.services.scan_log_store import fetch_scans, scan_gap_days

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


async def assemble_history(user_id: str, *, days: int = 30) -> HistoryResponse:
    store = get_evidence_store()
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    scans = await fetch_scans(user_id, since=since)

    if not scans:
        return HistoryResponse(
            user_id=user_id,
            days=days,
            scan_count=0,
            message="Building your history — check back after a few daily scans.",
            workbook_version=store.workbook_version,
        )

    prior_since = since - timedelta(days=days)
    prior_scans = await fetch_scans(user_id, since=prior_since)
    prior_scans = [
        s
        for s in prior_scans
        if _parse_dt(s.get("scanned_at")) < since
    ]

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
    if len(scans) < 7:
        message = "Building your history — check back in a week for trend insights."

    return HistoryResponse(
        user_id=user_id,
        days=days,
        scan_count=len(scans),
        sfi_average=sfi_avg,
        sfi_prior_period_average=sfi_prior,
        sfi_delta_vs_prior=sfi_delta,
        sudden_events=sudden_events,
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
