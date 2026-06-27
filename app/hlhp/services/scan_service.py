"""HLHP v2 scan orchestration — env, matching, Outdoor-OK, response assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.hlhp.core.bands import bucketize_environment
from app.hlhp.core.phase import DayPhase, phase_used_label, resolve_day_phase
from app.hlhp.core.profile_mode import resolve_mode
from app.hlhp.core.season import indian_season
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.evidence.matcher import match_findings
from app.hlhp.evidence.nuggets import rotate_nuggets
from app.hlhp.evidence.ranker import rank_findings, select_fire_budget, _select_diverse
from app.hlhp.evidence.voice import apply_lay_voice
from app.hlhp.coach.assembler import assemble_coach_wrap
from app.hlhp.coach.feature_flag import coach_voice_enabled
from app.hlhp.coach.forecast import ForecastSnapshot, get_forecast
from app.hlhp.coach.nugget_rotation import pick_fresh_nugget
from app.hlhp.coach.rotation import filter_by_recency, prefer_fresh_archetypes
from app.hlhp.coach.state_store import (
    fetch_selected_symptoms,
    load_coach_context,
    record_nugget_shown,
    record_surfaced_rules,
    record_symptom_tap,
)
from app.hlhp.coach.models import CoachWrap
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.scan import (
    AlertTile,
    EnvSnapshot,
    ScanRequest,
    ScanResponse,
    ScienceNuggetOut,
    SfiFactorCard,
    SymptomChip,
    SymptomTapRequest,
    SymptomTapResponse,
    WeatherVisuals,
)
from app.hlhp.services.alert_generator import generate_alert
from app.hlhp.services.outdoor_ok import compute_outdoor_ok, pick_mood_verdict
from app.hlhp.services.profile_personalizer import personalize_alert
from app.hlhp.services.scoring_engine import calculate_skin_score
from app.hlhp.services.profile_loader import (
    diagnose_skin_profile,
    load_merged_profile_doc,
    load_user_first_name,
    load_user_profile,
)
from app.hlhp.services.concern_resolver import concern_slug_from_profile
from app.hlhp.services.severity import severity_for_finding
from app.hlhp.services.weather_fetcher import fetch_environmental_data
from app.hlhp.services.weather_visuals import extract_weather_visuals
from app.hlhp.composition.alert_copy import (
    compose_alert_title,
    compose_how_routine,
    compose_outlook_subline,
    compose_strip_headline,
    pick_alert_body,
    pick_did_you_know_for_tile,
)
from app.hlhp.composition.vocabulary import mood_headline, symptom_chips
from app.hlhp.composition.forecast import forecast_oneliner
from app.hlhp.composition.lane_state import resolve_lane_states
from app.hlhp.composition.feeds import seasonal_tags_for_city
from app.hlhp.composition.delta import compute_env_delta, match_sudden_breakout_alerts
from app.hlhp.services.consent_store import env_logging_allowed
from app.hlhp.services.scan_log_store import env_baseline_7d, record_scan_log

_ROUTINE_LABELS = {
    "apply_sunscreen": "Broad-spectrum sunscreen as a daily habit",
    "reapply_sunscreen": "Reapply sunscreen through outdoor hours",
    "cleanse_gentle": "Gentle gel cleanser",
    "cleanse_oil": "Oil cleanse first, then gel cleanser",
    "double_cleanse": "Double cleanse in the evening",
    "layer_hydration": "Hydrating serum underneath moisturizer",
    "layer_barrier": "Barrier-repair moisturizer",
    "layer_antioxidant": "Antioxidant serum in the morning",
    "layer_brightening": "Brightening serum on marks",
    "apply_retinoid_pm": "Retinoid at night, built up slowly",
    "take_supplement": "Oral supplement per your clinician",
}

# Kept for legacy references; HOW copy is composed in composition.alert_copy.

_GUEST_NUDGE = (
    "Create a profile to unlock concern-specific alerts tailored to your skin."
)
_INCOMPLETE_PROFILE_NUDGE = "Complete your skin profile to get personalised alerts."


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

_BAND_SFI = {
    "uvi": {
        "off": (5, "Low", "Minimal UV load today."),
        "low": (15, "Low", "Light UV — basics still help."),
        "moderate": (40, "Moderate", "UV is active — sunscreen matters."),
        "high": (60, "Strong", "Post-acne marks darken faster without sunscreen today."),
        "very_high": (80, "Strong", "High UV — protection really helps."),
        "extreme": (95, "Extreme", "Extreme UV — head-to-toe protection helps most."),
    },
    "temp": {
        "very_cold": (70, "Cold snap", "Barrier stress from cold air."),
        "cold": (50, "Cool", "Cooler air can tighten skin."),
        "comfortable": (10, "Comfortable", "Temperature is skin-friendly."),
        "warm": (35, "Warm", "Warmth lifts sebum slightly."),
        "hot": (65, "Hot afternoon", "Sebum runs warmer; jaw and chin shine by mid-day."),
        "very_hot": (85, "Very hot", "Heat pushes sebum and sweat hard."),
    },
    "aqi": {
        "good": (10, "Clean", "Air is clean for skin."),
        "satisfactory": (25, "Mostly clean", "Light particulate — background pressure on skin."),
        "moderate": (45, "Moderate", "Pollution adds oxidative load."),
        "poor": (65, "Poor", "Particulate stress is meaningful today."),
        "very_poor": (80, "Very poor", "Heavy pollution day."),
        "severe": (95, "Severe", "Severe air — limit prolonged outdoor exposure."),
    },
    "humidity": {
        "very_low": (55, "Very dry", "Low humidity pulls water from skin."),
        "low": (35, "Dry", "Dry air increases transepidermal water loss."),
        "comfortable": (15, "Comfortable", "Balanced moisture in the air."),
        "high": (45, "Muggy", "Humidity lifts sebum and stickiness."),
        "very_high": (70, "Muggy, rising", "Fungal-acne risk on chest and back climbs this week."),
    },
}


def _sfi_factor_cards(bands) -> list[SfiFactorCard]:
    cards = []
    for factor, table_key, attr in (
        ("Sun strength", "uvi", "uvi"),
        ("Heat", "temp", "temperature"),
        ("Air quality", "aqi", "aqi"),
        ("Air moisture", "humidity", "humidity"),
    ):
        band = getattr(bands, attr)
        table = _BAND_SFI.get(table_key, {})
        pct, label, impact = table.get(band, (30, band.replace("_", " ").title(), ""))
        cards.append(
            SfiFactorCard(factor=factor, label=label, skin_impact=impact, severity_pct=pct)
        )
    return cards


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
    store,
    bands,
    mood: str,
    env: EnvironmentalData,
    city: str,
    local_time: datetime,
    profile: UserProfile | None,
    guest_mode: bool,
    alert_count: int,
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
    for row in match_sudden_breakout_alerts(
        city=city, month=local_time.month, delta=delta, composition=store.composition
    ):
        ext = str(row.get("mood_verdict_extension") or "")
        if ext and ext not in sudden:
            sudden.append(ext.replace("_", " "))

    oneliner = forecast_oneliner(bands=bands, concern_id=concern, mood=mood)
    first_name = ""
    if user_id:
        try:
            first_name = await load_user_first_name(user_id)
        except Exception:
            first_name = ""
    oneliner = _personalize_forecast(oneliner, first_name or None, guest_mode)

    label = None
    if alert_count == 1 and concern:
        label = f"1 {concern.replace('_', ' ')} alert"
    elif alert_count == 1:
        label = "1 alert for today"
    elif alert_count and concern:
        label = f"{alert_count} {concern.replace('_', ' ')} alerts"
    elif alert_count:
        label = f"{alert_count} alerts ready"

    selected_symptoms: set[str] = set()
    if user_id:
        selected_symptoms = await fetch_selected_symptoms(user_id)

    return {
        "workbook_version": store.workbook_version,
        "user_first_name": first_name or None,
        "mood_headline": mood_headline(mood),
        "forecast_oneliner": oneliner or None,
        "sudden_event_tags": sudden[:5],
        "alert_count_label": label,
        "symptom_chips": [
            SymptomChip(**c)
            for c in symptom_chips(concern, selected=selected_symptoms)
        ],
        "lane_state_ctas": resolve_lane_states(
            alert_count=alert_count,
            sudden_event=bool(sudden),
            mood_verdict=mood,
            when=local_time,
        ),
        "sfi_factor_cards": _sfi_factor_cards(bands),
    }


def _weather_fields(env: EnvironmentalData) -> dict:
    visuals = extract_weather_visuals(env.raw_weather_payload)
    return {
        "weather_visuals": WeatherVisuals(**visuals),
        "skin_care_tip": visuals.get("skin_care_tip"),
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
    """Display label for the strip — prefer Skintruth area+city+state over client city-only."""
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


def _finding_to_tile(
    finding,
    *,
    guest_mode: bool,
    day_phase: DayPhase,
    bands,
    glossary: list[dict],
    coach_wrap: CoachWrap | None = None,
    profile: UserProfile | None = None,
    routine_framework: list[dict] | None = None,
) -> AlertTile:
    body = apply_lay_voice(
        pick_alert_body(finding, guest_mode=guest_mode, day_phase=day_phase),
        glossary,
    )
    title = compose_alert_title(finding) or body.split(".")[0].strip() or body
    phase_label = phase_used_label(finding.time_of_day_phase, day_phase)
    how = compose_how_routine(
        routine_framework or [],
        finding,
        profile=profile,
        day_phase=day_phase,
    )
    did_you_know = pick_did_you_know_for_tile(finding, body=body)
    return AlertTile(
        rule_id=finding.id,
        severity=severity_for_finding(finding, bands),
        l1=title,
        l2=body,
        phase_used=phase_label,  # type: ignore[arg-type]
        mood_verdict_tag=finding.mood_verdict_tag or "",
        engagement_archetype=finding.engagement_archetype or "",
        symptom_keyword=finding.symptom_keyword or None,
        routine_action=finding.routine_action or "",
        how_text=how,
        did_you_know=did_you_know,
        visual_icon_hint=finding.visual_icon_hint or "",
        physical_analogy=finding.physical_analogy or None,
        body_sensation_decode=finding.body_sensation_decode or None,
        source_citation=finding.science_citation,
        factor=finding.factor,
        coach_wrap=coach_wrap,
    )


def _build_legacy_alert(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool,
):
    """Same alert shape as GET /api/hl/v1/alert and /api/hl/v2/alert."""
    score = calculate_skin_score(env)
    generic = generate_alert(env, score)
    if profile is None or guest_mode:
        return generic
    mode = resolve_mode(profile).value
    if mode in ("personalised", "partial_personalised"):
        try:
            return personalize_alert(generic, profile, env, score)
        except Exception:
            pass
    return generic


def _baseline_alert_tile(
    *,
    mood: str,
    mood_headline_text: str | None,
    forecast_oneliner: str | None,
    outdoor_band: str | None,
    day_phase: DayPhase,
    how_text: str | None = None,
) -> AlertTile:
    """Fallback when no evidence rule fires — still show today's guidance in the modal."""
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
    store = get_evidence_store()
    env = await resolve_environment(req)
    guest_mode = req.user_id is None
    profile: UserProfile | None = None
    if req.user_id:
        profile = await load_user_profile(req.user_id, auth_user=auth_user)
        guest_mode = resolve_mode(profile).value == "guest"

    day_phase = resolve_day_phase(req.local_time)
    partial = bool(profile and not guest_mode and resolve_mode(profile).value == "partial_personalised")
    profile_nudge = await _resolve_profile_nudge(
        guest_mode=guest_mode,
        user_id=req.user_id,
        auth_user=auth_user,
    )
    bands = bucketize_environment(env)
    season = indian_season()

    candidates = match_findings(
        store.findings,
        season=season,
        bands=bands,
        profile=profile,
        guest_mode=guest_mode,
        partial_personalised=partial,
        index=store.index,
        day_phase=day_phase,
    )

    env_snapshot = _build_env_snapshot(env, user_id=req.user_id, city=req.city, local_time=req.local_time)
    outdoor_ok, band_text = compute_outdoor_ok(env)

    if not candidates:
        mood = pick_mood_verdict(bands)
        ui = await _scan_ui_enrichment(
            store=store,
            bands=bands,
            mood=mood,
            env=env,
            city=req.city,
            local_time=req.local_time,
            profile=profile,
            guest_mode=guest_mode,
            alert_count=0,
            user_id=req.user_id,
        )
        legacy_alert = _build_legacy_alert(env, profile, guest_mode=guest_mode)
        strip_line = compose_strip_headline(
            None,
            mood_headline_text=ui.get("mood_headline"),
            forecast_oneliner=ui.get("forecast_oneliner"),
            outdoor_band=band_text,
            guest_mode=guest_mode,
            day_phase=day_phase,
            personalised=not guest_mode,
        )
        resp = ScanResponse(
            snapshot_version=str(store.version),
            workbook_version=ui.pop("workbook_version"),
            mode="guest" if guest_mode else "personalised",
            env_snapshot=env_snapshot,
            outdoor_ok_score=outdoor_ok,
            outdoor_ok_band_text=band_text,
            mood_verdict_today=mood,
            alerts=[],
            legacy_alert=legacy_alert,
            strip_headline=strip_line,
            profile_nudge=profile_nudge,
            raw_weather_payload=env.raw_weather_payload or None,
            **_weather_fields(env),
            **ui,
        )
        await _maybe_record_scan(req=req, response=resp, env=env, profile=profile, guest_mode=guest_mode)
        return resp

    candidate_pool = candidates
    coach_ctx = None
    forecast: ForecastSnapshot | None = None
    use_coach = (
        coach_voice_enabled(req.user_id)
        and req.user_id
        and profile
        and not guest_mode
    )
    if use_coach:
        coach_ctx = await load_coach_context(
            req.user_id, profile, local_time=req.local_time, severity="SOFT_ENV"
        )
        pool = filter_by_recency(candidate_pool, coach_ctx.suppressed_rule_ids)
        ranked = rank_findings(
            pool,
            profile=profile,
            partial_personalised=partial,
            day_phase=day_phase,
            guest_mode=guest_mode,
            bands=bands,
        )
        ranked = prefer_fresh_archetypes(ranked, coach_ctx.recent_archetypes)
        if req.latitude is not None and req.longitude is not None:
            forecast = await get_forecast(req.latitude, req.longitude)
    else:
        ranked = rank_findings(
            candidate_pool,
            profile=profile,
            partial_personalised=partial,
            day_phase=day_phase,
            guest_mode=guest_mode,
            bands=bands,
        )

    headlines, swipe_candidates = select_fire_budget(
        ranked,
        guest_mode=guest_mode,
        day_phase=day_phase,
        profile=profile,
        bands=bands,
    )

    if not headlines:
        full_ranked = rank_findings(
            candidate_pool,
            profile=profile,
            partial_personalised=partial,
            day_phase=day_phase,
            guest_mode=guest_mode,
            bands=bands,
        )
        if full_ranked:
            headlines = _select_diverse(full_ranked, max_slots=1)

    primary_tag = headlines[0].mood_verdict_tag if headlines else ""
    mood = pick_mood_verdict(bands, primary_tag)

    findings_by_id = {f.id: f for f in headlines + swipe_candidates}
    routine_framework = (store.composition or {}).get("concern_routine_framework") or []

    def _wrap_for(finding) -> CoachWrap | None:
        if not coach_ctx:
            return None
        return assemble_coach_wrap(
            finding,
            coach_ctx,
            uvi_band=bands.uvi,
            day_phase=day_phase,
            mood_verdict=mood,
            forecast=forecast,
            env_uvi=env.uv_index,
            env_aqi=env.aqi,
            local_time=req.local_time,
        )

    alerts = [
        _finding_to_tile(
            f,
            guest_mode=guest_mode,
            day_phase=day_phase,
            bands=bands,
            glossary=store.glossary,
            coach_wrap=_wrap_for(f),
            profile=profile,
            routine_framework=routine_framework,
        )
        for f in headlines
    ]
    candidate_tiles = [
        _finding_to_tile(
            f,
            guest_mode=guest_mode,
            day_phase=day_phase,
            bands=bands,
            glossary=store.glossary,
            coach_wrap=_wrap_for(f) if coach_ctx else None,
            profile=profile,
            routine_framework=routine_framework,
        )
        for f in swipe_candidates
    ]

    nugget_out: ScienceNuggetOut | None = None
    if use_coach and coach_ctx:
        fresh = pick_fresh_nugget(
            store.nuggets,
            seen_ids=coach_ctx.seen_nugget_ids,
            mood_factor=headlines[0].factor if headlines else None,
        )
        if fresh:
            nugget_out = ScienceNuggetOut(
                id=fresh.id, text=fresh.text, factor=fresh.factor, source=fresh.source
            )
            await record_nugget_shown(req.user_id, fresh.id)
        await record_surfaced_rules(req.user_id, headlines, surfaced_at=req.local_time)
    else:
        rotated = rotate_nuggets(
            store.nuggets,
            count=1,
            user_id=req.user_id,
            factor=headlines[0].factor if headlines else None,
        )
        if rotated:
            n = rotated[0]
            nugget_out = ScienceNuggetOut(id=n.id, text=n.text, factor=n.factor, source=n.source)

    ui = await _scan_ui_enrichment(
        store=store,
        bands=bands,
        mood=mood,
        env=env,
        city=req.city,
        local_time=req.local_time,
        profile=profile,
        guest_mode=guest_mode,
        alert_count=len(alerts),
        user_id=req.user_id,
    )
    if not alerts:
        how_baseline = None
        if profile and not guest_mode and routine_framework and candidate_pool:
            how_baseline = compose_how_routine(
                routine_framework,
                candidate_pool[0],
                profile=profile,
                day_phase=day_phase,
            )
        forecast_for_strip = ui.get("forecast_oneliner")
        alerts = [
            _baseline_alert_tile(
                mood=mood,
                mood_headline_text=ui.get("mood_headline"),
                forecast_oneliner=forecast_for_strip,
                outdoor_band=band_text,
                day_phase=day_phase,
                how_text=how_baseline,
            )
        ]
        if not guest_mode:
            ui["alert_count_label"] = "1 alert for today"
    else:
        forecast_for_strip = ui.get("forecast_oneliner")
    if alerts and not guest_mode:
        top = alerts[0]
        enriched = compose_outlook_subline(
            forecast_oneliner=forecast_for_strip,
            how_text=top.how_text,
            alert_l2=top.l2,
            guest_mode=False,
        )
        if enriched:
            ui["forecast_oneliner"] = enriched
            forecast_for_strip = enriched
    legacy_alert = _build_legacy_alert(env, profile, guest_mode=guest_mode)
    strip_line = compose_strip_headline(
        headlines[0] if headlines else None,
        mood_headline_text=ui.get("mood_headline"),
        forecast_oneliner=forecast_for_strip,
        outdoor_band=band_text,
        guest_mode=guest_mode,
        day_phase=day_phase,
        personalised=not guest_mode,
    )

    resp = ScanResponse(
        snapshot_version=str(store.version),
        workbook_version=ui.pop("workbook_version"),
        mode="guest" if guest_mode else "personalised",
        concern_id=concern_slug_from_profile(profile) if not guest_mode else None,
        env_snapshot=env_snapshot,
        outdoor_ok_score=outdoor_ok,
        outdoor_ok_band_text=band_text,
        mood_verdict_today=mood,
        alerts=alerts,
        candidate_alerts=candidate_tiles,
        legacy_alert=legacy_alert,
        science_nugget=nugget_out,
        strip_headline=strip_line,
        profile_nudge=profile_nudge,
        raw_weather_payload=env.raw_weather_payload or None,
        **_weather_fields(env),
        **ui,
    )
    await _maybe_record_scan(req=req, response=resp, env=env, profile=profile, guest_mode=guest_mode)
    return resp


async def run_symptom_tap(req: SymptomTapRequest) -> SymptomTapResponse:
    store = get_evidence_store()
    env = await resolve_environment(req)
    guest_mode = req.user_id is None
    profile: UserProfile | None = None
    if req.user_id:
        profile = await load_user_profile(req.user_id)

    day_phase = resolve_day_phase(req.local_time)
    bands = bucketize_environment(env)
    keyword = req.symptom_keyword.strip().lower()

    matched = [
        f
        for f in match_findings(
            store.findings,
            season=indian_season(),
            bands=bands,
            profile=profile,
            guest_mode=guest_mode,
            index=store.index,
            day_phase=day_phase,
        )
        if (f.symptom_keyword or "").strip().lower() == keyword
    ]
    if not matched and keyword:
        matched = [
            f
            for f in store.findings
            if (f.symptom_keyword or "").strip().lower() == keyword and f.is_surfaced_to_client()
        ][:5]

    routine_framework = (store.composition or {}).get("concern_routine_framework") or []
    tiles = [
        _finding_to_tile(
            f,
            guest_mode=guest_mode,
            day_phase=day_phase,
            bands=bands,
            glossary=store.glossary,
            profile=profile,
            routine_framework=routine_framework,
        )
        for f in matched[:3]
    ]

    if not matched:
        return SymptomTapResponse(
            headline=f"Noticing {keyword.replace('_', ' ')}?",
            decode_text="Today's environment can shift how skin feels hour to hour — hydration and barrier support usually help.",
            tip="Tap refresh on the home screen after a few hours outdoors.",
            source_locator="HLHP Evidence Base",
            matched_rules=[],
        )

    best = matched[0]
    decode = best.body_sensation_decode or best.pick_l2() or best.mechanism
    headline = f"Still {keyword.replace('_', ' ')}?" if day_phase == "evening" else f"{keyword.replace('_', ' ').title()} right now?"
    tip = best.physical_analogy or best.product_implication or "Barrier support and gentle cleansing help more than overwashing."

    continuity_ack = None
    if req.user_id and profile and not guest_mode:
        await record_symptom_tap(req.user_id, keyword, req.local_time)
        try:
            ctx = await load_coach_context(req.user_id, profile, local_time=req.local_time)
            if (
                ctx.last_symptom_keyword == keyword
                and ctx.last_symptom_at
                and (req.local_time.date() - ctx.last_symptom_at.date()).days >= 1
            ):
                continuity_ack = (
                    f"You felt this yesterday too — {keyword.replace('_', ' ')} on repeat days "
                    "often tracks with sustained heat or humidity."
                )
        except Exception:
            pass

    return SymptomTapResponse(
        headline=headline,
        decode_text=decode,
        tip=tip,
        source_locator=best.science_citation,
        matched_rules=tiles,
        continuity_acknowledgment=continuity_ack,
    )
