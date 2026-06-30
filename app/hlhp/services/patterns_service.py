"""Mine symptom–environment patterns from real user logs (rule-based statistics, no ML)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from app.hlhp.coach.state_store import fetch_daily_feeling_keywords
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.patterns import PatternInsight, PatternsResponse
from app.hlhp.services.daily_log_store import RETENTION_DAYS, fetch_daily_logs

logger = logging.getLogger(__name__)

MIN_LOGS_REQUIRED = 30
MIN_SYMPTOM_DAYS = 3
MIN_CO_DAYS = 3
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
    "humidity_surge": "humidity surge days",
    "heat_surge": "heat surge days",
    "uv_surge": "UV surge days",
    "pollution_surge": "poor-air spike days",
    "humidity_high": "high-humidity days",
    "uv_high": "high-UV days",
    "aqi_poor": "poor-air days",
    "hot_day": "hot days",
    "low_sfi": "low SFI days",
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
class DayRecord:
    date: str
    feelings: set[str] = field(default_factory=set)
    rh_pct: Optional[float] = None
    uvi: Optional[float] = None
    aqi: Optional[int] = None
    temp_c: Optional[float] = None
    sfi: Optional[int] = None
    sudden_tags: set[str] = field(default_factory=set)
    weekday: int = 0
    feeling_hours: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class DriverRule:
    key: str
    label: str
    test: Callable[[DayRecord], bool]


def _driver_rules() -> list[DriverRule]:
    return [
        DriverRule(
            "humidity_surge",
            "humidity surge days",
            lambda d: "humidity_surge" in d.sudden_tags,
        ),
        DriverRule(
            "heat_surge",
            "heat surge days",
            lambda d: "heat_surge" in d.sudden_tags,
        ),
        DriverRule(
            "uv_surge",
            "UV surge days",
            lambda d: "uv_surge" in d.sudden_tags,
        ),
        DriverRule(
            "pollution_surge",
            "pollution spike days",
            lambda d: "pollution_surge" in d.sudden_tags,
        ),
        DriverRule(
            "humidity_high",
            "high humidity (RH above 75%)",
            lambda d: d.rh_pct is not None and d.rh_pct > 75,
        ),
        DriverRule(
            "uv_high",
            "high UV (index 8 or above)",
            lambda d: d.uvi is not None and d.uvi >= 8,
        ),
        DriverRule(
            "aqi_poor",
            "poor air quality (AQI above 100)",
            lambda d: d.aqi is not None and d.aqi > 100,
        ),
        DriverRule(
            "hot_day",
            "hot outdoor days (32°C or above)",
            lambda d: d.temp_c is not None and d.temp_c >= 32,
        ),
        DriverRule(
            "low_sfi",
            "low skin-friendliness (SFI below 50)",
            lambda d: d.sfi is not None and d.sfi < 50,
        ),
    ]


async def _feeling_hours_by_day(user_id: str, since: datetime) -> dict[str, list[int]]:
    from app.hlhp.db import hl_db

    out: dict[str, list[int]] = {}
    try:
        cursor = hl_db["hlhp_symptom_feeling_log"].find(
            {"user_id": user_id, "recorded_at": {"$gte": since}, "selected": True},
        )
        async for doc in cursor:
            recorded = _parse_dt(doc.get("recorded_at"))
            day = recorded.date().isoformat()
            out.setdefault(day, []).append(recorded.hour)
    except Exception as exc:
        logger.warning("HLHP pattern feeling hours fetch failed: %s", exc)
    return out


def _build_day_records(
    daily_docs: list[dict[str, Any]],
    feelings_by_day: dict[str, list[str]],
    hours_by_day: dict[str, list[int]],
    *,
    span_days: int,
    now: datetime,
) -> list[DayRecord]:
    by_date: dict[str, DayRecord] = {}
    for doc in daily_docs:
        date_key = str(doc.get("date") or "")
        if not date_key:
            continue
        try:
            wd = datetime.strptime(date_key, "%Y-%m-%d").date().weekday()
        except ValueError:
            wd = 0
        avg = doc.get("outdoor_score_avg")
        by_date[date_key] = DayRecord(
            date=date_key,
            feelings=set(),
            rh_pct=float(doc["rh_pct"]) if doc.get("rh_pct") is not None else None,
            uvi=float(doc["uvi"]) if doc.get("uvi") is not None else None,
            aqi=int(doc["aqi"]) if doc.get("aqi") is not None else None,
            temp_c=float(doc["temp_c"]) if doc.get("temp_c") is not None else None,
            sfi=int(round(float(avg))) if avg is not None else None,
            sudden_tags={str(t) for t in (doc.get("sudden_event_tags") or []) if t},
            weekday=wd,
        )

    for date_key, keywords in feelings_by_day.items():
        rec = by_date.setdefault(
            date_key,
            DayRecord(
                date=date_key,
                weekday=datetime.strptime(date_key, "%Y-%m-%d").date().weekday()
                if _valid_date(date_key)
                else 0,
            ),
        )
        for kw in keywords:
            rec.feelings.add(kw.strip().lower().replace(" ", "_"))

    for date_key, hours in hours_by_day.items():
        rec = by_date.setdefault(
            date_key,
            DayRecord(
                date=date_key,
                weekday=datetime.strptime(date_key, "%Y-%m-%d").date().weekday()
                if _valid_date(date_key)
                else 0,
            ),
        )
        rec.feeling_hours = hours

    # Fill calendar window so weekday rates are fair
    end = now.date()
    start = end - timedelta(days=span_days - 1)
    records: list[DayRecord] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        records.append(
            by_date.get(key)
            or DayRecord(date=key, weekday=cursor.weekday())
        )
        cursor += timedelta(days=1)
    return records


def _valid_date(key: str) -> bool:
    try:
        datetime.strptime(key, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _symptom_days(records: list[DayRecord], symptom: str) -> list[DayRecord]:
    return [r for r in records if symptom in r.feelings]


def _evaluate(
    records: list[DayRecord],
    symptom: str,
    rule: DriverRule,
) -> Optional[dict[str, Any]]:
    symptom_days = _symptom_days(records, symptom)
    n_symptom = len(symptom_days)
    if n_symptom < MIN_SYMPTOM_DAYS:
        return None

    n_days = len(records)
    n_driver_all = sum(1 for d in records if rule.test(d))
    n_both = sum(1 for d in symptom_days if rule.test(d))

    if n_both == 0:
        return None

    p_given_symptom = n_both / n_symptom
    baseline = n_driver_all / n_days if n_days else 0
    match_pct = round(100 * p_given_symptom)
    baseline_pct = round(100 * baseline)

    if match_pct < MIN_MATCH_PCT:
        return None
    if n_both < MIN_CO_DAYS:
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
        "symptom_days": symptom_days,
    }


def _timeline_series(records: list[DayRecord], symptom: str, rule: DriverRule) -> list[int]:
    series: list[int] = []
    for day in records:
        has_symptom = symptom in day.feelings
        has_driver = rule.test(day)
        if has_symptom and has_driver:
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
        return f"All {n_symptom} days you logged {sym} lined up with {driver}."
    return f"{n_both} of {n_symptom} {sym} log days lined up with {driver}."


async def assemble_patterns(user_id: str, *, days: int = RETENTION_DAYS) -> PatternsResponse:
    store = get_evidence_store()
    now = datetime.now(timezone.utc)
    span = min(max(1, days), RETENTION_DAYS)
    since = now - timedelta(days=span)

    feelings_by_day = await fetch_daily_feeling_keywords(user_id, since=since)
    hours_by_day = await _feeling_hours_by_day(user_id, since)
    daily_docs = await fetch_daily_logs(user_id, since=since, limit=span)

    records = _build_day_records(
        daily_docs,
        feelings_by_day,
        hours_by_day,
        span_days=span,
        now=now,
    )

    logged_days = sum(1 for r in records if r.feelings)
    all_symptoms: set[str] = set()
    for r in records:
        all_symptoms.update(r.feelings)

    if logged_days < MIN_LOGS_REQUIRED:
        return PatternsResponse(
            user_id=user_id,
            days=span,
            log_count=logged_days,
            min_logs_required=MIN_LOGS_REQUIRED,
            patterns=[],
            message=(
                f"Patterns unlock after {MIN_LOGS_REQUIRED} days of log. "
                "Keep logging daily to build your track."
            ),
            workbook_version=store.workbook_version,
        )

    candidates: list[dict[str, Any]] = []
    rules = _driver_rules()

    for symptom in sorted(all_symptoms):
        for rule in rules:
            hit = _evaluate(records, symptom, rule)
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
                timeline=_timeline_series(records, symptom, rule),
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
        log_count=logged_days,
        min_logs_required=MIN_LOGS_REQUIRED,
        patterns=patterns,
        message=message,
        workbook_version=store.workbook_version,
    )
