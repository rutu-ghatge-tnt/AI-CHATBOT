"""HLHP v2 scan orchestration — live env + v3.5 scenario library."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.phase import DayPhase, resolve_day_phase
from app.hlhp.core.profile_mode import resolve_mode
from app.hlhp.core.season import indian_season
from app.hlhp.evidence.scenario_store import ScenarioStore, get_scenario_store
from app.hlhp.coach.models import CoachWrap
from app.hlhp.coach.state_store import (
    fetch_selected_symptoms,
    record_symptom_tap,
)
from app.hlhp.core.local_date import calendar_date
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.scan import (
    AlertTile,
    EnvSnapshot,
    EvidenceCellOut,
    FlashAlertOut,
    ImpactLineOut,
    ScanRequest,
    ScanResponse,
    ScienceNuggetOut,
    SfiFactorCard,
    SymptomChip,
    SymptomTapRequest,
    SymptomTapResponse,
    WeatherVisuals,
)
from app.hlhp.services.routine_today_service import select_routine_today
from app.hlhp.services.scenario_engine import (
    ScenarioEvaluation,
    evaluate_scenario,
    points_to_level,
    severity_for_risk,
)
from app.hlhp.services.profile_loader import (
    diagnose_skin_profile,
    load_merged_profile_doc,
    load_user_first_name,
    load_user_profile,
)
from app.hlhp.services.concern_resolver import concern_slug_from_profile
from app.hlhp.services.weather_fetcher import fetch_environmental_data
from app.hlhp.services.weather_visuals import extract_weather_visuals
from app.hlhp.services.v4_scoring_engine import V4Evaluation
from app.hlhp.services.sfi_unified import resolve_sfi
from app.hlhp.composition.vocabulary import mood_headline, symptom_chips
from app.hlhp.composition.lane_state import resolve_lane_states
from app.hlhp.composition.feeds import seasonal_tags_for_city
from app.hlhp.composition.delta import compute_env_delta
from app.hlhp.services.consent_store import env_logging_allowed
from app.hlhp.services.scan_log_store import env_baseline_7d, record_scan_log
from app.hlhp.services.surge_detector import assess_surge

_GUEST_NUDGE = (
    "Create a profile to unlock concern-specific alerts tailored to your skin."
)
_INCOMPLETE_PROFILE_NUDGE = "Complete your skin profile to get personalised alerts."

_BAND_MOOD = {
    "Paradise Mode": "easy_day",
    "Smooth Sailing": "comfortable_day",
    "Guard Up": "manageable_day",
    "Battle Stations": "combo_stress_day",
    "Hostile Mode": "surge_day",
    "Code Red": "surge_day",
}

_NIGHT_BLOCK = ("sunscreen", "spf", "sun screen")


def _env_for_scenario(env: EnvironmentalData, force_surge: bool) -> EnvironmentalData:
    """Surge demo: stress env for SFI/alerts only — weather visuals stay on real readings."""
    if not force_surge:
        return env
    return env.model_copy(
        update={
            "temperature_c": max(env.temperature_c, 38.0),
            "aqi": max(env.aqi, 380),
            "uv_index": max(env.uv_index, 11.0),
        }
    )


def _mood_for_band(band: str) -> str:
    return _BAND_MOOD.get(band, "routine_day")


def _severity_pct_for_points(points: int) -> int:
    level = points_to_level(points)
    return {"Low": 22, "Medium": 55, "High": 88}[level]


async def _scenario_coach_wrap(
    *,
    user_id: str | None,
    guest_mode: bool,
    env: EnvironmentalData,
    scenario,
    local_time: datetime,
    first_name: str | None,
) -> CoachWrap | None:
    if guest_mode or not user_id:
        return None
    from app.hlhp.services.engagement_service import calendar_streak, counting_dates

    today = calendar_date(local_time) if local_time else date.today()
    dates = await counting_dates(user_id)
    current = calendar_streak(dates, today)
    effort = None
    if current >= 1:
        effort = (
            f"Day {current} of showing up. Your skin notices the consistency."
        )
    greeting = None
    if first_name and resolve_day_phase(local_time) == "morning":
        greeting = f"Good morning, {first_name}"
    from app.hlhp.coach.models import StreakMeta

    return CoachWrap(
        greeting=greeting,
        effort_recognition=effort,
        forward_hook=scenario.flash_alert.l0,
        streak_meta=StreakMeta(current=current, longest=current) if current else None,
    )


def _scenario_alert_tile(
    scenario: ScenarioEvaluation,
    *,
    day_phase: DayPhase,
) -> AlertTile:
    cell = scenario.cell or {}
    body = scenario.flash_alert.l1 or scenario.flash_alert.l0
    title = scenario.flash_alert.l0 or (body.split(".")[0].strip() if body else scenario.band)
    if day_phase == "evening":
        lower = f"{title} {body}".lower()
        if any(tok in lower for tok in _NIGHT_BLOCK):
            body = scenario.flash_alert.tip or body
            title = scenario.band
    pmids = scenario.evidence_cell.pmids if scenario.evidence_cell else []
    phase_label = "evening_recovery" if day_phase == "evening" else "morning_prep"
    archetype = {
        "master": "SCENARIO_V34_MASTER",
        "compound": "SCENARIO_V34_COMPOUND",
        "guest_single": "SCENARIO_V34_GUEST",
        "guest_compound": "SCENARIO_V34_GUEST_COMPOUND",
    }.get(scenario.cell_kind, "SCENARIO_V34")
    factor = scenario.dominant.factor
    if scenario.compound_name:
        factor = scenario.compound_name
    elif scenario.evidence_cell and scenario.evidence_cell.factor:
        factor = scenario.evidence_cell.factor
    return AlertTile(
        rule_id=str(cell.get("id", "scenario_master")),
        severity=severity_for_risk(scenario.risk),
        l1=title,
        l2=body,
        phase_used=phase_label,  # type: ignore[arg-type]
        mood_verdict_tag=_mood_for_band(scenario.band),
        engagement_archetype=archetype,
        how_text=scenario.flash_alert.tip,
        source_citation="|".join(pmids) if pmids else "SkinBB HLHP Scenario Library v3.5",
        factor=factor,
    )


_V4_DRIVER_KEYS = {
    "Temperature": "temp",
    "UV": "uv",
    "Humidity": "humidity",
    "AQI": "aqi",
}
_V4_DRIVER_NAMES = {
    "Temperature": "Heat",
    "UV": "UV",
    "Humidity": "Humidity",
    "AQI": "Air (AQI)",
}


def _scenario_scan_fields(
    store: ScenarioStore,
    scenario: ScenarioEvaluation,
    v4_eval: V4Evaluation,
    *,
    profile: UserProfile | None = None,
    guest_mode: bool = False,
) -> dict:
    flash = scenario.flash_alert
    ev = scenario.evidence_cell
    return {
        "sfi": v4_eval.environmental_sfi,
        "personal_sfi": v4_eval.personal_sfi,
        "band": v4_eval.mode,
        "action_cluster": scenario.action_cluster,
        "whats_different": select_routine_today(
            v4_eval, profile, guest_mode=guest_mode
        ),
        "risk": scenario.risk,
        "risk_label": scenario.risk_label,
        "confidence": scenario.confidence,
        "flash_alert": FlashAlertOut(
            level=flash.level,
            mode=v4_eval.mode,  # type: ignore[arg-type]
            l0=flash.l0,
            l1=flash.l1,
            tip=flash.tip,
        ),
        "impacts": [
            ImpactLineOut(
                driver=_V4_DRIVER_KEYS[d.factor],  # type: ignore[arg-type]
                name=_V4_DRIVER_NAMES[d.factor],
                level=d.level,
                value=d.value,
            )
            for d in v4_eval.drivers
        ],
        "evidence_cell": (
            EvidenceCellOut(
                id=ev.id,
                factor=ev.factor,
                band=ev.band,
                evidence=ev.evidence,
                pmids=ev.pmids,
                confidence=ev.confidence,
                action=ev.action,
            )
            if ev
            else None
        ),
        "scenario_library_version": store.version,
        "time_window": scenario.time_window,
        "outdoor_ok_score": v4_eval.headline_sfi,
        "outdoor_ok_band_text": v4_eval.mode,
    }


def _sfi_factor_cards_from_v4(v4_eval: V4Evaluation) -> list[SfiFactorCard]:
    return [
        SfiFactorCard(
            factor=_V4_DRIVER_NAMES[d.factor],
            label=d.label,
            skin_impact=f"{_V4_DRIVER_NAMES[d.factor]} in the {d.label.lower()} band today.",
            severity_pct=_severity_pct_for_points(d.points),
        )
        for d in v4_eval.drivers
    ]


def _pick_scenario_nugget(
    store: ScenarioStore,
    scenario: ScenarioEvaluation,
    user_id: Optional[str],
) -> ScienceNuggetOut | None:
    factor = scenario.dominant.factor
    pool = [n for n in store.nuggets if (n.get("factor") or "").lower() == factor.lower()]
    if not pool:
        pool = list(store.nuggets)
    if not pool:
        return None
    idx = hash((user_id or "guest", factor, scenario.sfi)) % len(pool)
    n = pool[idx]
    return ScienceNuggetOut(
        id=int(n.get("n", 0)),
        text=str(n.get("text", "")),
        factor=str(n.get("factor", "")),
        source=str(n.get("source", "")),
    )


async def _resolve_profile_nudge(
    *,
    guest_mode: bool,
    user_id: Optional[str],
    auth_user: dict | None = None,
) -> str | None:
    if not guest_mode:
        return None
    if not user_id:
        return _GUEST_NUDGE
    try:
        doc = await load_merged_profile_doc(user_id, auth_user=auth_user)
        diagnosis = diagnose_skin_profile(doc)
        if not diagnosis.get("ready"):
            return str(diagnosis.get("message") or _INCOMPLETE_PROFILE_NUDGE)
    except Exception:
        pass
    return _GUEST_NUDGE


def _personalize_forecast(oneliner: str | None, first_name: str | None, guest_mode: bool) -> str | None:
    if not oneliner:
        return None
    text = oneliner.strip()
    if guest_mode or not first_name:
        return text
    lower = text.lower()
    if lower.startswith(first_name.lower()):
        return text
    return f"{first_name}, {text[0].lower()}{text[1:]}" if text else text


async def _scan_ui_enrichment(
    *,
    scenario: ScenarioEvaluation,
    v4_eval: V4Evaluation,
    env: EnvironmentalData,
    city: str,
    local_time: datetime,
    profile: UserProfile | None,
    guest_mode: bool,
    user_id: Optional[str] = None,
) -> dict:
    concern = concern_slug_from_profile(profile)
    baseline = None
    if user_id:
        baseline = await env_baseline_7d(user_id, before=local_time)
    delta = compute_env_delta(
        env.uv_index, env.temperature_c, env.aqi, env.humidity_pct, baseline=baseline
    )
    sudden = list(seasonal_tags_for_city(city, local_time))
    sudden.extend(delta.sudden_tags)
    sudden.extend(scenario.sudden_event_tags)

    oneliner = scenario.flash_alert.l1
    first_name = ""
    if user_id:
        try:
            first_name = await load_user_first_name(user_id)
        except Exception:
            first_name = ""
    oneliner = _personalize_forecast(oneliner, first_name or None, guest_mode)

    mood = _mood_for_band(v4_eval.mode)
    selected_symptoms: set[str] = set()
    if user_id:
        selected_symptoms = await fetch_selected_symptoms(user_id)

    return {
        "user_first_name": first_name or None,
        "mood_headline": mood_headline(mood),
        "forecast_oneliner": oneliner or None,
        "sudden_event_tags": list(dict.fromkeys(sudden))[:5],
        "alert_count_label": "1 alert for today",
        "symptom_chips": [
            SymptomChip(**c)
            for c in symptom_chips(concern, selected=selected_symptoms)
        ],
        "lane_state_ctas": resolve_lane_states(
            alert_count=1,
            sudden_event=bool(sudden),
            mood_verdict=mood,
            when=local_time,
        ),
        "sfi_factor_cards": _sfi_factor_cards_from_v4(v4_eval),
    }


def _weather_fields(env: EnvironmentalData) -> dict:
    """Pass through Skintruth weather API payload + extracted FE visuals unchanged."""
    payload = env.raw_weather_payload or {}
    visuals = extract_weather_visuals(payload if payload else None)
    return {
        "weather_visuals": WeatherVisuals(**visuals),
        "skin_care_tip": visuals.get("skin_care_tip"),
        "weather_api_url": env.weather_api_url or None,
        "raw_weather_payload": payload if payload else None,
    }


async def _maybe_record_scan(
    *,
    req: ScanRequest,
    response: ScanResponse,
    env: EnvironmentalData,
    profile: UserProfile | None,
    guest_mode: bool,
) -> None:
    if not req.user_id or guest_mode:
        return
    if not await env_logging_allowed(req.user_id):
        return
    try:
        await record_scan_log(
            user_id=req.user_id,
            scanned_at=req.local_time,
            city=req.city,
            mode=response.mode,
            outdoor_ok_score=response.outdoor_ok_score,
            mood_verdict=response.mood_verdict_today,
            sudden_event_tags=response.sudden_event_tags,
            uvi=env.uv_index,
            temp_c=env.temperature_c,
            aqi=env.aqi,
            rh_pct=env.humidity_pct,
            alert_rule_ids=[a.rule_id for a in response.alerts],
            concern_id=concern_slug_from_profile(profile),
            snapshot_version=response.snapshot_version,
            latitude=req.latitude,
            longitude=req.longitude,
        )
    except Exception:
        pass


async def resolve_environment(req) -> EnvironmentalData:
    city = getattr(req, "city", None) or getattr(req, "location_city", "Unknown")
    local_time = getattr(req, "local_time", None) or getattr(req, "current_time", datetime.now(timezone.utc))
    if req.latitude is not None and req.longitude is not None:
        env = await fetch_environmental_data(req.latitude, req.longitude)
        if city and env.location_name in ("Unknown", ""):
            return env.model_copy(update={"location_name": city})
        return env
    raw_uvi = getattr(req, "raw_uvi", None)
    if raw_uvi is None:
        raw_uvi = 5.0
    return EnvironmentalData(
        uv_index=float(raw_uvi),
        temperature_c=float(getattr(req, "raw_temp", None) or 25.0),
        aqi=int(getattr(req, "raw_aqi", None) or 50),
        humidity_pct=float(getattr(req, "raw_rh", None) or 50.0),
        location_name=city,
        fetched_at=local_time if isinstance(local_time, datetime) else datetime.now(timezone.utc),
        data_sources={"weather": "client_raw", "aqi": "client_raw", "uv": "client_raw"},
    )


def _snapshot_city_label(env: EnvironmentalData, req_city: str) -> str:
    api_name = (env.location_name or "").strip()
    if api_name and api_name not in ("Unknown", ""):
        return api_name
    return (req_city or "").strip() or "Unknown"


def _build_env_snapshot(
    env: EnvironmentalData,
    *,
    user_id: Optional[str],
    city: str,
    local_time: datetime,
) -> EnvSnapshot:
    bands = bucketize_environment(env)
    ts = local_time.isoformat()
    if local_time.tzinfo is None:
        ts = local_time.replace(tzinfo=timezone.utc).isoformat()
    return EnvSnapshot(
        user_id=user_id,
        city=_snapshot_city_label(env, city),
        timestamp=ts,
        uvi=env.uv_index,
        aqi_cpcb=env.aqi,
        rh_pct=env.humidity_pct,
        temp_c=env.temperature_c,
        season=indian_season(local_time.date() if hasattr(local_time, "date") else None),
        uvi_band=bands.uvi,
        aqi_band=bands.aqi,
        rh_band=bands.humidity,
        temp_band=bands.temperature,
    )


def _baseline_alert_tile(
    *,
    mood: str,
    mood_headline_text: str | None,
    forecast_oneliner: str | None,
    outdoor_band: str | None,
    day_phase: DayPhase,
    how_text: str | None = None,
) -> AlertTile:
    title = (mood_headline_text or mood_headline(mood)).strip()
    body = (forecast_oneliner or outdoor_band or "Sunscreen and gentle cleansing still help on calmer days.").strip()
    phase_label = "evening_recovery" if day_phase == "evening" else "morning_prep"
    return AlertTile(
        rule_id="baseline_day_outlook",
        severity="SOFT_ENV",
        l1=title,
        l2=body,
        phase_used=phase_label,  # type: ignore[arg-type]
        mood_verdict_tag=mood,
        engagement_archetype="BASELINE",
        how_text=how_text,
        source_citation="Skin Beyond Borders HLHP",
        factor="environment",
    )


async def run_scan(req: ScanRequest, *, auth_user: dict | None = None) -> ScanResponse:
    scenario_store = get_scenario_store()
    env = await resolve_environment(req)
    guest_mode = req.user_id is None
    profile: UserProfile | None = None
    if req.user_id:
        profile = await load_user_profile(req.user_id, auth_user=auth_user)
        guest_mode = resolve_mode(profile).value == "guest"

    day_phase = resolve_day_phase(req.local_time)
    profile_nudge = await _resolve_profile_nudge(
        guest_mode=guest_mode,
        user_id=req.user_id,
        auth_user=auth_user,
    )

    scenario_env = _env_for_scenario(env, req.force_surge)
    baseline = None
    if req.user_id:
        baseline = await env_baseline_7d(req.user_id, before=req.local_time or datetime.now(timezone.utc))
    surge_assessment = assess_surge(env, baseline=baseline, force=req.force_surge)
    surge_active = surge_assessment.active

    v4_eval = resolve_sfi(
        scenario_env,
        profile,
        guest_mode=guest_mode,
        surge=surge_active,
    )
    scenario = evaluate_scenario(
        scenario_store,
        scenario_env,
        city=req.city,
        profile=profile,
        guest_mode=guest_mode,
        force_surge=surge_active,
        local_time=req.local_time,
    )
    env_snapshot = _build_env_snapshot(env, user_id=req.user_id, city=req.city, local_time=req.local_time)
    ui = await _scan_ui_enrichment(
        scenario=scenario,
        v4_eval=v4_eval,
        env=env,
        city=req.city,
        local_time=req.local_time,
        profile=profile,
        guest_mode=guest_mode,
        user_id=req.user_id,
    )
    coach_wrap = await _scenario_coach_wrap(
        user_id=req.user_id,
        guest_mode=guest_mode,
        env=env,
        scenario=scenario,
        local_time=req.local_time,
        first_name=ui.get("user_first_name"),
    )
    alert = _scenario_alert_tile(scenario, day_phase=day_phase)
    if coach_wrap is not None:
        alert = alert.model_copy(update={"coach_wrap": coach_wrap})
    nugget_out = _pick_scenario_nugget(scenario_store, scenario, req.user_id)
    mood = _mood_for_band(v4_eval.mode)
    strip_line = scenario.flash_alert.l0 or mood_headline(mood)

    resp = ScanResponse(
        snapshot_version=scenario_store.version,
        workbook_version=scenario_store.source,
        mode="guest" if guest_mode else "personalised",
        concern_id=concern_slug_from_profile(profile) if not guest_mode else None,
        env_snapshot=env_snapshot,
        mood_verdict_today=mood,
        alerts=[alert],
        candidate_alerts=[],
        science_nugget=nugget_out,
        strip_headline=strip_line,
        profile_nudge=profile_nudge,
        **_weather_fields(env),
        **ui,
        **_scenario_scan_fields(
            scenario_store,
            scenario,
            v4_eval,
            profile=profile,
            guest_mode=guest_mode,
        ),
        scene=v4_eval.scene,
    )
    await _maybe_record_scan(req=req, response=resp, env=env, profile=profile, guest_mode=guest_mode)
    return resp


_SYMPTOM_SCENARIO_HINTS: dict[str, str] = {
    "oily": "Oil output often tracks heat and humidity — lighter layers usually feel better.",
    "dry": "Dry air pulls water from skin — barrier support helps more than extra washing.",
    "dull": "Pollution and UV can flatten glow — antioxidant habits and shade matter.",
    "breakout": "Heat and humidity can clog pores faster — keep cleansing gentle, not aggressive.",
    "spots": "Marks linger after breakouts — sun and pollution can deepen them.",
    "itchy": "Dry or humid swings can irritate skin — cool rinses and soft fabrics help.",
    "red": "Heat and pollution can fan redness — calm barrier care beats harsh scrubs.",
}


async def run_symptom_tap(req: SymptomTapRequest) -> SymptomTapResponse:
    scenario_store = get_scenario_store()
    env = await resolve_environment(req)
    guest_mode = req.user_id is None
    profile: UserProfile | None = None
    if req.user_id:
        profile = await load_user_profile(req.user_id)

    day_phase = resolve_day_phase(req.local_time)
    keyword = req.symptom_keyword.strip().lower()
    scenario = evaluate_scenario(
        scenario_store,
        env,
        city=req.city,
        profile=profile,
        guest_mode=guest_mode,
        local_time=req.local_time,
    )
    tile = _scenario_alert_tile(scenario, day_phase=day_phase)
    decode = _SYMPTOM_SCENARIO_HINTS.get(
        keyword,
        f"Today's {scenario.dominant.name.lower()} reading can shift how skin feels hour to hour.",
    )
    headline = (
        f"Still {keyword.replace('_', ' ')}?"
        if day_phase == "evening"
        else f"{keyword.replace('_', ' ').title()} right now?"
    )
    tip = scenario.flash_alert.tip or "Tap refresh on the home screen after a few hours outdoors."
    source = tile.source_citation

    continuity_ack = None
    if req.user_id and profile and not guest_mode:
        await record_symptom_tap(req.user_id, keyword, req.local_time)

    return SymptomTapResponse(
        headline=headline,
        decode_text=decode,
        tip=tip,
        source_locator=source,
        matched_rules=[tile],
        continuity_acknowledgment=continuity_ack,
    )
