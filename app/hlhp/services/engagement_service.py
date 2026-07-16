"""HLHP engagement features: unified log write, calendar streak, weekly card, learn."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from app.hlhp.core.local_date import calendar_date, calendar_date_key, today_local
from app.hlhp.core.profile_mode import resolve_mode

from app.hlhp.coach.state_store import fetch_selected_symptoms, record_symptom_feeling
from app.hlhp.composition.explore import pick_learn_nuggets
from app.hlhp.composition.symptom import assemble_symptom_explainer
from app.hlhp.composition.vocabulary import symptom_chips
from app.hlhp.core.bands import EnvironmentBands, bucketize_environment
from app.hlhp.services.concern_resolver import resolve_concern_id
from app.hlhp.core.sfi_driver import bands_snapshot, driver_key_from_env
from app.hlhp.evidence.composition_store import get_composition_store
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.engagement import (
    FeelingLogStatus,
    LearnExplainerOut,
    LearnNuggetOut,
    LearnResponse,
    LearnSymptomChipOut,
    LoggedEventOut,
    StreakBadges,
    StreakResponse,
    UserLogRequest,
    UserLogResponse,
    WeekGridDay,
    WeeklyCardResponse,
    WeeklySeriesPoint,
)
from app.hlhp.models.scan import ScanRequest
from app.hlhp.services.action_tap_service import run_action_tap
from app.hlhp.services.daily_log_store import fetch_daily_logs, upsert_user_log_day
from app.hlhp.services.log_event_store import (
    FeelingLogCooldownError,
    assert_feeling_log_allowed,
    count_log_events,
    fetch_feeling_log_status,
    fetch_latest_log_session,
    fetch_log_event_dates,
    insert_log_event,
)
from app.hlhp.services.profile_loader import load_user_profile
from app.hlhp.services.sfi_unified import headline_sfi, resolve_sfi
from app.hlhp.services.v4_scoring_engine import clamp_sfi, feeling_log_sfi_adjustment
from app.hlhp.services.scan_service import resolve_environment
from app.hlhp.coach.models import ActionTapRequest
from app.hlhp.db_errors import HlhpStoreError

logger = logging.getLogger(__name__)

_SYMPTOM_ALLOW = frozenset({"normal", "dry", "oily", "dull", "breakout", "spots"})
_NEEDS_AREA = {"breakout", "spots"}


def validate_log_symptoms(symptoms: list[str], areas: list[str]) -> tuple[list[str], list[str]]:
    """V4 log rules: vocabulary, normal/full_face exclusivity, areas for breakout/spots."""
    out = _normalize_symptoms(symptoms)
    if not out:
        raise HTTPException(status_code=400, detail="At least one symptom required")
    unknown = [s for s in out if s not in _SYMPTOM_ALLOW]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown symptoms: {', '.join(unknown)}")
    if "normal" in out and len(out) > 1:
        raise HTTPException(status_code=400, detail="'normal' is exclusive — remove other symptoms")

    norm_areas = _normalize_areas(areas)
    if "full_face" in norm_areas and len(norm_areas) > 1:
        raise HTTPException(status_code=400, detail="'full_face' is exclusive of specific zones")
    if _NEEDS_AREA.intersection(out) and not norm_areas:
        raise HTTPException(status_code=400, detail="areas required for breakout / spots")
    return out, norm_areas if _NEEDS_AREA.intersection(out) else []


def _parse_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_symptoms(symptoms: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in symptoms:
        kw = s.strip().lower().replace(" ", "_")
        if kw and kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out


def _normalize_areas(areas: list[str]) -> list[str]:
    return [
        a.strip().lower().replace(" ", "_")
        for a in areas
        if a.strip()
    ]


async def counting_dates(user_id: str, *, lookback_days: int = 400) -> set[str]:
    """Dates that count toward the calendar streak (daily activity or log events)."""
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    dates = await fetch_log_event_dates(user_id, limit=lookback_days)
    daily_docs = await fetch_daily_logs(user_id, since=since, limit=lookback_days)
    for doc in daily_docs:
        day = str(doc.get("date") or "")
        if not day:
            continue
        if doc.get("user_logged") or int(doc.get("scan_count") or 0) > 0:
            dates.add(day)
    return dates


def calendar_streak(dates: set[str], today: date) -> int:
    n = 0
    d = today
    while d.isoformat() in dates:
        n += 1
        d -= timedelta(days=1)
    return n


def longest_calendar_streak(dates: set[str]) -> int:
    if not dates:
        return 0
    sorted_days = sorted(date.fromisoformat(d) for d in dates)
    longest = 1
    current = 1
    for i in range(1, len(sorted_days)):
        if (sorted_days[i] - sorted_days[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return max(longest, current)


def week_grid(dates: set[str], today: date) -> list[WeekGridDay]:
    out: list[WeekGridDay] = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        iso = d.isoformat()
        out.append(
            WeekGridDay(
                date=iso,
                done=iso in dates,
                today=i == 0,
            )
        )
    return out


async def assemble_streak(user_id: str, *, today: date | None = None) -> StreakResponse:
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    profile = await load_user_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Complete your skin profile first")

    today = today or today_local()
    dates = await counting_dates(user_id)
    current = calendar_streak(dates, today)
    longest = max(longest_calendar_streak(dates), current)
    log_count = await count_log_events(user_id)

    badges = StreakBadges(
        first_log=log_count >= 1,
        streak_7=current >= 7,
        streak_30=current >= 30,
    )
    if current < 7:
        nxt = 7 - current
    elif current < 30:
        nxt = 30 - current
    else:
        nxt = 0

    return StreakResponse(
        current_streak=current,
        longest_streak=longest,
        badges=badges,
        days_to_next_badge=max(nxt, 0),
        week_grid=week_grid(dates, today),
    )


async def assemble_weekly_card(user_id: str) -> WeeklyCardResponse:
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=14)
    docs = await fetch_daily_logs(user_id, since=since, limit=30)
    by_date = {str(d.get("date") or ""): d for d in docs if d.get("date")}

    def series_for(days_back_end: int, days_back_start: int) -> list[WeeklySeriesPoint]:
        out: list[WeeklySeriesPoint] = []
        today = now.date()
        for i in range(days_back_end, days_back_start - 1, -1):
            d = today - timedelta(days=i)
            iso = d.isoformat()
            avg = by_date.get(iso, {}).get("outdoor_score_avg")
            sfi = int(round(float(avg))) if avg is not None else None
            out.append(WeeklySeriesPoint(date=iso, sfi=sfi))
        return out

    cur_series = series_for(6, 0)
    prev_series = series_for(13, 7)
    cur_vals = [p.sfi for p in cur_series if p.sfi is not None]
    prev_vals = [p.sfi for p in prev_series if p.sfi is not None]
    avg = round(sum(cur_vals) / len(cur_vals)) if cur_vals else None
    pavg = round(sum(prev_vals) / len(prev_vals)) if prev_vals else None
    trend = (avg - pavg) if avg is not None and pavg is not None else None

    return WeeklyCardResponse(
        week_avg_sfi=avg,
        trend_vs_prev=trend,
        series=cur_series,
        logged_days=len(cur_vals),
    )


async def assemble_learn(
    user_id: str,
    *,
    city: str | None = None,
    concern_id: str | None = None,
    bands: EnvironmentBands | None = None,
) -> LearnResponse:
    profile = await load_user_profile(user_id) if user_id else None
    resolved_concern = resolve_concern_id(profile=profile, client_concern_id=concern_id)
    resolved_city = (city or "India").strip()

    selected: set[str] = set()
    if user_id:
        selected = await fetch_selected_symptoms(user_id)
    keywords = sorted(selected)[:5]

    explainers: list[LearnExplainerOut] = []
    for kw in keywords:
        page = assemble_symptom_explainer(kw)
        if not page:
            continue
        explainers.append(
            LearnExplainerOut(
                keyword=page["symptom_keyword"],
                title=kw.replace("_", " ").title(),
                sections=[
                    {"heading": s.get("label"), "body": s.get("body")}
                    for s in page.get("sections", [])
                ],
            )
        )

    comp_store = get_composition_store()
    scenario_store = get_scenario_store()
    now = datetime.now().astimezone()
    rotation_rows = comp_store.composition.get("daily_nuggets_rotation") or []
    ranked = pick_learn_nuggets(
        rotation_rows,
        city=resolved_city,
        concern_id=resolved_concern,
        profile=profile,
        user_id=user_id,
        when=now,
        bands=bands,
        limit=6,
    )
    nuggets: list[LearnNuggetOut] = []
    for idx, row in enumerate(ranked):
        text = str(row.get("nugget_text") or "").strip()
        if not text:
            continue
        raw_id = row.get("nugget_id")
        try:
            nid = int(str(raw_id).replace("nug_", "")) if raw_id is not None else idx + 1
        except ValueError:
            nid = idx + 1
        nuggets.append(
            LearnNuggetOut(
                id=nid,
                text=text,
                factor=str(row.get("factor") or "Humidity"),
                source=str(row.get("source") or "SkinBB evidence base"),
            )
        )

    if not nuggets:
        for row in (scenario_store.nuggets or [])[:6]:
            text = row.get("text") if isinstance(row, dict) else ""
            if not str(text).strip():
                continue
            nid = int(row.get("n", 0) or 0)
            factor = str(row.get("factor") or "")
            source = str(row.get("source") or "SkinBB HLHP Scenario Library v3.5")
            nuggets.append(LearnNuggetOut(id=nid, text=str(text), factor=factor, source=source))

    symptom_keywords = [
        LearnSymptomChipOut(keyword=str(c["keyword"]), highlighted=bool(c.get("highlighted")))
        for c in symptom_chips(resolved_concern, selected=selected)
    ]

    return LearnResponse(
        explainers=explainers,
        nuggets=nuggets,
        concern_id=resolved_concern,
        city=resolved_city,
        symptom_keywords=symptom_keywords,
    )


async def run_user_log(
    body: UserLogRequest,
    *,
    bearer_token: str | None = None,
) -> UserLogResponse:
    profile = await load_user_profile(body.user_id)
    guest_mode = profile is None or resolve_mode(profile).value == "guest"

    symptoms, areas = validate_log_symptoms(body.symptoms, body.areas)

    when = _parse_dt(body.local_time)
    date_key = calendar_date_key(when)

    latest = await fetch_latest_log_session(body.user_id)
    last_ts = latest.get("ts") if latest else None
    try:
        assert_feeling_log_allowed(last_ts, when)
    except FeelingLogCooldownError as exc:
        from app.hlhp.api.errors import feeling_log_cooldown_detail
        from app.hlhp.services.log_event_store import FEELING_LOG_COOLDOWN_HOURS

        raise HTTPException(
            status_code=429,
            detail=feeling_log_cooldown_detail(
                next_log_at=exc.next_log_at.isoformat(),
                retry_after_seconds=exc.retry_after_seconds,
                cooldown_hours=FEELING_LOG_COOLDOWN_HOURS,
            ),
        ) from exc

    scan_req = ScanRequest(
        user_id=body.user_id,
        city=body.location_city,
        local_time=when,
        latitude=body.latitude,
        longitude=body.longitude,
        raw_uvi=body.raw_uvi,
        raw_aqi=body.raw_aqi,
        raw_rh=body.raw_rh,
        raw_temp=body.raw_temp,
    )
    env = await resolve_environment(scan_req)
    bands = bucketize_environment(env)
    band_fields = bands_snapshot(bands)
    sfi_base = int(
        body.outdoor_ok_score
        if body.outdoor_ok_score is not None
        else headline_sfi(env, profile, guest_mode=guest_mode)
    )
    log_delta = feeling_log_sfi_adjustment(
        symptoms=symptoms,
        outdoor_exposure=body.outdoor_exposure,
        notes=body.notes,
    )
    sfi = clamp_sfi(sfi_base + log_delta)
    driver = driver_key_from_env(env, profile, guest_mode=guest_mode)
    sudden_tags = [str(t) for t in (body.sudden_event_tags or []) if t]

    session_id = await insert_log_event(
        {
            "ts": when,
            "date": date_key,
            "user_id": body.user_id,
            "symptoms": symptoms,
            "areas": areas,
            "sfi": sfi,
            "action_cluster": body.routine_action.strip() or "Maintain",
            **band_fields,
            "driver": driver,
            "uvi": float(env.uv_index),
            "temp_c": float(env.temperature_c),
            "aqi": int(env.aqi),
            "rh_pct": float(env.humidity_pct),
            "city": str(body.location_city or env.location_name or ""),
            "mood_verdict": str(body.mood_verdict or ""),
            "sudden_event_tags": sudden_tags,
            "outdoor_exposure": body.outdoor_exposure,
            "notes": (body.notes or "").strip() or None,
        }
    )

    for kw in symptoms:
        await record_symptom_feeling(
            body.user_id,
            kw,
            selected=True,
            recorded_at=when,
            session_id=session_id,
        )

    await upsert_user_log_day(
        user_id=body.user_id,
        logged_at=when,
        outdoor_ok_score=sfi,
        mood_verdict=str(body.mood_verdict or ""),
        sudden_event_tags=body.sudden_event_tags,
        uvi=float(env.uv_index),
        temp_c=float(env.temperature_c),
        aqi=int(env.aqi),
        rh_pct=float(env.humidity_pct),
        city=str(body.location_city or env.location_name or ""),
        bands=bands,
        driver=driver,
        areas=areas,
    )

    try:
        tap_req = ActionTapRequest(
            user_id=body.user_id,
            routine_action=body.routine_action,
            rule_id=body.rule_id,
            current_time=when,
            location_city=body.location_city,
            latitude=body.latitude,
            longitude=body.longitude,
            raw_uvi=body.raw_uvi,
            raw_aqi=body.raw_aqi,
            raw_rh=body.raw_rh,
            raw_temp=body.raw_temp,
            outdoor_ok_score=sfi,
            mood_verdict=body.mood_verdict,
            sudden_event_tags=body.sudden_event_tags,
        )
        await run_action_tap(tap_req)
    except HlhpStoreError:
        raise
    except Exception as exc:
        logger.warning("HLHP action_tap during log save skipped: %s", exc)

    dates = await counting_dates(body.user_id)
    current = calendar_streak(dates, calendar_date(when))
    longest = max(longest_calendar_streak(dates), current)

    logged_out = LoggedEventOut(
        ts=when.isoformat(),
        date=date_key,
        user_id=body.user_id,
        symptoms=symptoms,
        areas=areas,
        sfi=sfi,
        action_cluster=body.routine_action.strip() or "Maintain",
        temp_band=band_fields["temp_band"],
        uv_band=band_fields["uv_band"],
        aqi_band=band_fields["aqi_band"],
        humidity_band=band_fields["humidity_band"],
    )
    log_status = await fetch_feeling_log_status(body.user_id, at=when)

    try:
        from app.hlhp.services.patterns_engine_service import recompute_patterns_for_user

        await recompute_patterns_for_user(body.user_id)
    except Exception as exc:
        logger.warning("HLHP patterns recompute after log skipped: %s", exc)

    selfie_url = (body.selfie_url or "").strip() or None
    if not selfie_url:
        try:
            from app.hlhp.services.selfie_service import (
                get_selfie_for_date,
                public_selfie_url,
            )

            existing = await get_selfie_for_date(body.user_id, date_key)
            if existing and existing.get("s3_key"):
                selfie_url = public_selfie_url(str(existing["s3_key"]))
        except Exception as exc:
            logger.debug("HLHP selfie lookup for bus log skipped: %s", exc)

    try:
        from app.hlhp.services.daily_log_bus import publish_daily_log_best_effort

        await publish_daily_log_best_effort(
            body.user_id,
            symptoms=symptoms,
            areas=areas,
            sfi=sfi,
            notes=(body.notes or "").strip() or None,
            outdoor_exposure=body.outdoor_exposure,
            selfie=bool(selfie_url),
            selfie_url=selfie_url,
            streak=current,
            date_key=date_key,
            doctor_id=body.doctor_id,
            bearer_token=bearer_token,
            ts_ms=int(when.timestamp() * 1000),
        )
    except Exception as exc:
        logger.warning("HLHP daily_log bus side-effect skipped: %s", exc)

    return UserLogResponse(
        logged=logged_out,
        streak=current,
        longest_streak=longest,
        feeling_log=FeelingLogStatus(**log_status),
    )
