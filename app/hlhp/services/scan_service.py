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
from app.hlhp.evidence.ranker import rank_findings, select_fire_budget
from app.hlhp.evidence.voice import apply_lay_voice
from app.hlhp.coach.assembler import assemble_coach_wrap
from app.hlhp.coach.feature_flag import coach_voice_enabled
from app.hlhp.coach.forecast import ForecastSnapshot, get_forecast
from app.hlhp.coach.nugget_rotation import pick_fresh_nugget
from app.hlhp.coach.rotation import filter_by_recency, prefer_fresh_archetypes
from app.hlhp.coach.state_store import (
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
    SymptomTapRequest,
    SymptomTapResponse,
)
from app.hlhp.services.outdoor_ok import compute_outdoor_ok, pick_mood_verdict
from app.hlhp.services.profile_loader import load_user_profile
from app.hlhp.services.severity import severity_for_finding
from app.hlhp.services.weather_fetcher import fetch_environmental_data

_GUEST_NUDGE = (
    "Create a profile to unlock concern-specific alerts tailored to your skin."
)


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
        city=city or env.location_name,
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
) -> AlertTile:
    l1 = apply_lay_voice(finding.pick_l1(guest_mode=guest_mode, day_phase=day_phase), glossary)
    phase_label = phase_used_label(finding.time_of_day_phase, day_phase)
    return AlertTile(
        rule_id=finding.id,
        severity=severity_for_finding(finding, bands),
        l1=l1,
        l2=finding.pick_l2(),
        phase_used=phase_label,  # type: ignore[arg-type]
        mood_verdict_tag=finding.mood_verdict_tag or "",
        engagement_archetype=finding.engagement_archetype or "",
        symptom_keyword=finding.symptom_keyword or None,
        routine_action=finding.routine_action or "",
        visual_icon_hint=finding.visual_icon_hint or "",
        physical_analogy=finding.physical_analogy or None,
        body_sensation_decode=finding.body_sensation_decode or None,
        source_citation=finding.science_citation,
        factor=finding.factor,
        coach_wrap=coach_wrap,
    )


async def run_scan(req: ScanRequest) -> ScanResponse:
    store = get_evidence_store()
    env = await resolve_environment(req)
    guest_mode = req.user_id is None
    profile: UserProfile | None = None
    if req.user_id:
        profile = await load_user_profile(req.user_id)
        guest_mode = resolve_mode(profile).value == "guest"

    day_phase = resolve_day_phase(req.local_time)
    partial = bool(profile and not guest_mode and resolve_mode(profile).value == "partial_personalised")
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
        return ScanResponse(
            snapshot_version=str(store.version),
            mode="guest" if guest_mode else "personalised",
            env_snapshot=env_snapshot,
            outdoor_ok_score=outdoor_ok,
            outdoor_ok_band_text=band_text,
            mood_verdict_today=mood,
            alerts=[],
            profile_nudge=_GUEST_NUDGE if guest_mode else None,
        )

    ranked = rank_findings(candidates, profile=profile, partial_personalised=partial)

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
        candidates = filter_by_recency(candidates, coach_ctx.suppressed_rule_ids)
        ranked = rank_findings(candidates, profile=profile, partial_personalised=partial)
        ranked = prefer_fresh_archetypes(ranked, coach_ctx.recent_archetypes)
        if req.latitude is not None and req.longitude is not None:
            forecast = await get_forecast(req.latitude, req.longitude)

    headlines, swipe_candidates = select_fire_budget(ranked)

    primary_tag = headlines[0].mood_verdict_tag if headlines else ""
    mood = pick_mood_verdict(bands, primary_tag)

    findings_by_id = {f.id: f for f in headlines + swipe_candidates}

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

    return ScanResponse(
        snapshot_version=str(store.version),
        mode="guest" if guest_mode else "personalised",
        env_snapshot=env_snapshot,
        outdoor_ok_score=outdoor_ok,
        outdoor_ok_band_text=band_text,
        mood_verdict_today=mood,
        alerts=alerts,
        candidate_alerts=candidate_tiles,
        science_nugget=nugget_out,
        profile_nudge=_GUEST_NUDGE if guest_mode else None,
    )


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

    tiles = [
        _finding_to_tile(
            f, guest_mode=guest_mode, day_phase=day_phase, bands=bands, glossary=store.glossary
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
