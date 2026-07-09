"""HLHP V4 API orchestration — assembles prototype contract payloads."""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.hlhp.core.local_date import calendar_date_key, today_local
from app.hlhp.core.profile_mode import resolve_mode
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.scan import ScanRequest
from app.hlhp.models.v4_api import (
    V4AlertEvidence,
    V4AlertOut,
    V4DriverOut,
    V4LearnLeverOut,
    V4LearnResponse,
    V4LogRequest,
    V4LogResponse,
    V4RecapDay,
    V4RecapResponse,
    V4ShareResponse,
    V4SfiOut,
    V4TodayResponse,
    V4Weather,
)
from app.hlhp.patterns.hlhp_patterns_engine import Config as PatternsConfig
from app.hlhp.services.daily_log_store import fetch_daily_logs
from app.hlhp.services.engagement_service import (
    assemble_learn,
    assemble_weekly_card,
    run_user_log,
)
from app.hlhp.services.pattern_state_store import get_pattern_state
from app.hlhp.services.patterns_engine_service import recompute_patterns_for_user
from app.hlhp.services.profile_loader import load_user_profile
from app.hlhp.services.scenario_engine import (
    DriverState,
    build_flash_alert,
    resolve_alert_cell,
    resolve_library_concerns,
    resolve_skin,
)
from app.hlhp.services.scan_log_store import env_baseline_7d
from app.hlhp.services.surge_detector import assess_surge
from app.hlhp.services.log_event_store import fetch_latest_log_for_date
from app.hlhp.services.scan_service import resolve_environment
from app.hlhp.services.sfi_unified import resolve_sfi
from app.hlhp.services.v4_scoring_engine import V4Evaluation, feeling_log_sfi_adjustment, clamp_sfi, mode_for_sfi
from app.hlhp.models.engagement import UserLogRequest

logger = logging.getLogger(__name__)

_SYMPTOM_ALLOW = frozenset({"normal", "dry", "oily", "dull", "breakout", "spots"})
_NEEDS_AREA = frozenset({"breakout", "spots"})


def _v4_drivers_to_states(eval_: V4Evaluation) -> list[DriverState]:
    names = {
        "Temperature": "Heat",
        "UV": "UV",
        "Humidity": "Humidity",
        "AQI": "Air (AQI)",
    }
    keys = {
        "Temperature": "temp",
        "UV": "uv",
        "Humidity": "humidity",
        "AQI": "aqi",
    }
    return [
        DriverState(
            factor=d.factor,
            key=keys[d.factor],
            name=names[d.factor],
            value=d.value,
            band_label=d.label,
            band_key=d.key,
            band_range="",
            points=d.points,
        )
        for d in eval_.drivers
    ]


def _format_date_en_in(d: date) -> str:
    return f"{d.day} {calendar.month_abbr[d.month]}"


def _patterns_unlock_in(user_id: str, log_days_30: int) -> int:
    return max(0, PatternsConfig.UNLOCK_LOG_DAYS - log_days_30)


async def assemble_today(
    *,
    user_id: str | None,
    city: str,
    local_time: datetime,
    latitude: float | None = None,
    longitude: float | None = None,
    raw_uvi: float | None = None,
    raw_aqi: int | None = None,
    raw_rh: float | None = None,
    raw_temp: float | None = None,
    force_surge: bool = False,
    auth_user: dict | None = None,
) -> V4TodayResponse:
    req = ScanRequest(
        user_id=user_id,
        city=city,
        local_time=local_time,
        latitude=latitude,
        longitude=longitude,
        raw_uvi=raw_uvi,
        raw_aqi=raw_aqi,
        raw_rh=raw_rh,
        raw_temp=raw_temp,
        force_surge=force_surge,
    )
    env = await resolve_environment(req)
    baseline = None
    if user_id:
        baseline = await env_baseline_7d(user_id, before=local_time)

    surge_assessment = assess_surge(env, baseline=baseline, force=force_surge)
    surge_active = surge_assessment.active

    if force_surge:
        env = env.model_copy(
            update={
                "temperature_c": max(env.temperature_c, 38.0),
                "aqi": max(env.aqi, 380),
                "uv_index": max(env.uv_index, 11.0),
            }
        )

    profile: UserProfile | None = None
    guest_mode = user_id is None
    if user_id:
        profile = await load_user_profile(user_id, auth_user=auth_user)
        guest_mode = resolve_mode(profile).value == "guest"

    store = get_scenario_store()
    eval_ = resolve_sfi(
        env,
        profile,
        guest_mode=guest_mode,
        surge=surge_active,
    )
    drivers = _v4_drivers_to_states(eval_)
    skin = resolve_skin(profile, guest_mode)
    concerns = resolve_library_concerns(profile, guest_mode)
    zone = store.city_zone.get((city or "").lower())
    cell, cell_kind, compound_name = resolve_alert_cell(
        store,
        drivers,
        skin=skin,
        concern=concerns[0],
        guest_mode=guest_mode,
        zone=zone,
        concern_candidates=concerns,
    )
    flash = build_flash_alert(
        cell,
        band=eval_.mode,  # type: ignore[arg-type]
        surge=surge_active,
    )
    level = "L2" if surge_active else flash.level

    city_label = (env.location_name or city or "Unknown").split(",")[0].strip()
    day_key = calendar_date_key(local_time)

    env_sfi = eval_.environmental_sfi
    personal_sfi = eval_.personal_sfi
    headline_sfi = eval_.headline_sfi
    mode_name = eval_.mode

    if user_id:
        day_log = await fetch_latest_log_for_date(user_id, day_key)
        if day_log:
            log_delta = feeling_log_sfi_adjustment(
                symptoms=list(day_log.get("symptoms") or []),
                outdoor_exposure=day_log.get("outdoor_exposure"),
                notes=day_log.get("notes"),
            )
            if log_delta:
                env_sfi = clamp_sfi(env_sfi + log_delta)
                if personal_sfi is not None:
                    personal_sfi = clamp_sfi(personal_sfi + log_delta)
                    headline_sfi = personal_sfi
                else:
                    headline_sfi = clamp_sfi(headline_sfi + log_delta)
                mode_name = mode_for_sfi(headline_sfi)

    return V4TodayResponse(
        city=city_label,
        date=day_key,
        mode_of_use="guest" if guest_mode else "personal",
        weather=V4Weather(
            temp_c=round(env.temperature_c, 1),
            uv_index=round(env.uv_index, 1),
            humidity_pct=round(env.humidity_pct, 1),
            aqi=int(env.aqi),
            wind_kmh=round(env.wind_kmh, 1),
            wind_dir=env.wind_dir or "",
            gust_kmh=round(env.gust_kmh, 1),
        ),
        scene=eval_.scene,
        drivers=[
            V4DriverOut(
                factor=d.factor,
                band=d.key,
                points=d.points,
                level=d.level,
                dominant=d.dominant,
            )
            for d in eval_.drivers
        ],
        sfi=V4SfiOut(
            environmental=env_sfi,
            personal=personal_sfi,
            headline=headline_sfi,
        ),
        mode=mode_name,
        alert=V4AlertOut(
            level=level,  # type: ignore[arg-type]
            l0=flash.l0,
            l1=flash.l1,
            tip=flash.tip,
            evidence=V4AlertEvidence(
                confidence=str(cell.get("confidence", "")) if cell else "",
                pmids=list(cell.get("pmids") or []) if cell else [],
            ),
        ),
        compound=compound_name if cell_kind in {"compound", "guest_compound"} else None,
        surge=surge_active,
        surge_tags=surge_assessment.tags,
    )


async def run_v4_log(body: V4LogRequest, *, auth_user: dict | None = None) -> V4LogResponse:
    when = body.local_time or datetime.now(timezone.utc)
    if body.date:
        try:
            parsed = date.fromisoformat(body.date)
            when = datetime.combine(parsed, when.timetz() or datetime.min.time(), tzinfo=when.tzinfo)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD") from exc

    symptoms = [s.strip().lower().replace(" ", "_") for s in body.symptoms if s.strip()]
    areas = [a.strip().lower().replace(" ", "_") for a in body.areas if a.strip()]

    log_body = UserLogRequest(
        user_id=body.user_id,
        symptoms=symptoms,
        areas=areas,
        local_time=when,
        location_city=body.city,
        latitude=body.latitude,
        longitude=body.longitude,
        outdoor_exposure=body.outdoor_exposure,
        notes=body.notes,
    )
    result = await run_user_log(log_body)

    try:
        await recompute_patterns_for_user(body.user_id)
    except Exception as exc:
        logger.warning("V4 patterns recompute after log skipped: %s", exc)

    ps = await get_pattern_state(body.user_id)
    log_days_30 = ps.log_days_30 if ps else 0

    return V4LogResponse(
        streak=result.streak,
        log_days_30d=log_days_30,
        patterns_unlock_in=_patterns_unlock_in(body.user_id, log_days_30),
    )


async def assemble_recap(user_id: str, month: str) -> V4RecapResponse:
    """Month format: YYYY-MM."""
    try:
        year_s, month_s = month.split("-", 1)
        year, mon = int(year_s), int(month_s)
        if mon < 1 or mon > 12:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM") from exc

    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, mon + 1, 1) - timedelta(days=1)

    since = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    docs = await fetch_daily_logs(user_id, since=since, limit=62)
    by_date: dict[str, dict] = {}
    for doc in docs:
        day = str(doc.get("date") or "")
        if start.isoformat() <= day <= end.isoformat():
            by_date[day] = doc

    days: list[V4RecapDay] = []
    cur = start
    sfi_vals: list[int] = []
    while cur <= end:
        iso = cur.isoformat()
        doc = by_date.get(iso)
        avg = doc.get("outdoor_score_avg") if doc else None
        sfi = int(round(float(avg))) if avg is not None else None
        if sfi is not None:
            sfi_vals.append(sfi)
        days.append(
            V4RecapDay(
                date=iso,
                sfi=sfi,
                dominant_driver=str(doc.get("driver") or "") or None if doc else None,
            )
        )
        cur += timedelta(days=1)

    event_callouts: list[dict[str, Any]] = []
    for day, doc in sorted(by_date.items()):
        tags = doc.get("sudden_event_tags") or []
        if tags:
            event_callouts.append(
                {"date": day, "tags": tags, "sfi": doc.get("outdoor_score_avg")}
            )

    avg_sfi = round(sum(sfi_vals) / len(sfi_vals)) if sfi_vals else None

    prev_start = date(year - 1, 12, 1) if mon == 1 else date(year, mon - 1, 1)
    prev_mon = prev_start.month
    prev_year = prev_start.year
    prev_end = start - timedelta(days=1)
    prev_since = datetime.combine(prev_start, datetime.min.time(), tzinfo=timezone.utc)
    prev_docs = await fetch_daily_logs(user_id, since=prev_since, limit=62)
    prev_vals: list[int] = []
    for doc in prev_docs:
        day = str(doc.get("date") or "")
        if prev_start.isoformat() <= day <= prev_end.isoformat():
            avg = doc.get("outdoor_score_avg")
            if avg is not None:
                prev_vals.append(int(round(float(avg))))
    prev_avg = round(sum(prev_vals) / len(prev_vals)) if prev_vals else None

    verdict = None
    if avg_sfi is not None and prev_avg is not None:
        delta = avg_sfi - prev_avg
        if delta > 3:
            verdict = f"Stronger than {calendar.month_name[prev_mon]} — up {delta} points on average."
        elif delta < -3:
            verdict = f"Tougher than {calendar.month_name[prev_mon]} — down {abs(delta)} points on average."
        else:
            verdict = f"Steady compared to {calendar.month_name[prev_mon]}."

    return V4RecapResponse(
        month=month,
        days=days,
        event_callouts=event_callouts,
        verdict_vs_previous_month=verdict,
        avg_sfi=avg_sfi,
        prev_month_avg_sfi=prev_avg,
    )


def _share_caption(
    *,
    week_avg: int | None,
    trend: int | None,
    city: str,
    week_start: date,
    week_end: date,
) -> str:
    range_label = f"{_format_date_en_in(week_start)}–{_format_date_en_in(week_end)}"
    if week_avg is None:
        return f"{range_label}: your HLHP week — environment, not products."
    base = f"{range_label}: your skin environment averaged {week_avg}/100."
    if trend is not None:
        sign = "+" if trend >= 0 else ""
        base += f" {sign}{trend} from the week before."
    base += " Weather your skin met — no product push."
    if city:
        base += f" · {city}"
    return base


async def assemble_share(user_id: str, *, city: str = "") -> V4ShareResponse:
    card = await assemble_weekly_card(user_id)
    today = today_local()
    week_start = today - timedelta(days=6)
    week_end = today

    caption = _share_caption(
        week_avg=card.week_avg_sfi,
        trend=card.trend_vs_prev,
        city=city,
        week_start=week_start,
        week_end=week_end,
    )

    daily_values = [
        {"date": p.date, "sfi": p.sfi, "label": _format_date_en_in(date.fromisoformat(p.date))}
        for p in card.series
    ]

    return V4ShareResponse(
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        week_avg=card.week_avg_sfi,
        delta_vs_prev_7_days=card.trend_vs_prev,
        daily_values=daily_values,
        caption=caption,
    )


async def assemble_learn_v4(
    user_id: str,
    *,
    city: str | None = None,
    concern_id: str | None = None,
) -> V4LearnResponse:
    base = await assemble_learn(user_id, city=city, concern_id=concern_id)
    store = get_scenario_store()

    levers: list[V4LearnLeverOut] = []
    for row in (store.nutrition or [])[:4]:
        if not isinstance(row, dict):
            continue
        levers.append(
            V4LearnLeverOut(
                category="nutrition",
                label=str(row.get("label") or row.get("modifier") or "Nutrition"),
                body=str(row.get("body") or row.get("addendum") or row.get("action") or ""),
            )
        )
    for row in (store.lifestyle or [])[:4]:
        if not isinstance(row, dict):
            continue
        levers.append(
            V4LearnLeverOut(
                category="lifestyle",
                label=str(row.get("label") or row.get("modifier") or "Lifestyle"),
                body=str(row.get("body") or row.get("addendum") or row.get("action") or ""),
            )
        )

    return V4LearnResponse(
        explainers=[e.model_dump() for e in base.explainers],
        nuggets=[n.model_dump() for n in base.nuggets],
        levers=levers,
        concern_id=base.concern_id,
        city=base.city,
    )
