"""HLHP composition layer API routes (UI spec §10)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.hlhp.api.deps_auth import (
    hlhp_authenticated_user,
    hlhp_optional_authenticated_user,
    resolve_optional_personalization_user_id,
    verify_client_user_id,
)
from app.hlhp.api.store_http import http_503_for_store_error
from app.hlhp.db_errors import HlhpStoreError

from app.hlhp.composition.concern import assemble_concern_deepdive
from app.hlhp.composition.explore import assemble_event_guides, assemble_explore
from app.hlhp.composition.knowledge_feed_rank import rank_knowledge_feed_posts
from app.hlhp.core.bands import bucketize_environment
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.knowledge_feed_client import fetch_knowledge_feed_pool
from app.hlhp.composition.forecast import assemble_week_ahead
from app.hlhp.composition.plan_week import assemble_plan_week
from app.hlhp.composition.sfi_timeline import assemble_sfi_timeline
from app.hlhp.composition.symptom import assemble_symptom_explainer
from app.hlhp.evidence.composition_store import get_composition_store
from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.engagement import (
    FeelingLogStatus,
    LearnResponse,
    StreakResponse,
    UserLogRequest,
    UserLogResponse,
    WeeklyCardResponse,
)
from app.hlhp.models.history import ConsentRequest, ConsentResponse, ConsentStatusResponse
from app.hlhp.models.scan import ScanRequest
from app.hlhp.services.consent_store import get_consent, upsert_consent
from app.hlhp.coach.state_store import fetch_selected_symptoms
from app.hlhp.services.engagement_service import (
    assemble_learn,
    assemble_streak,
    assemble_weekly_card,
    run_user_log,
)
from app.hlhp.services.log_event_store import fetch_feeling_log_status
from app.hlhp.services.history_service import assemble_catchup, assemble_history
from app.hlhp.services.patterns_service import assemble_patterns
from app.hlhp.services.profile_loader import load_user_profile
from app.hlhp.services.scan_service import resolve_environment

router = APIRouter(prefix="/hlhp", tags=["HLHP v2 — Composition"])


@router.get("/concern_deepdive/{concern_id}")
async def concern_deepdive(concern_id: str):
    page = assemble_concern_deepdive(concern_id)
    if not page:
        raise HTTPException(status_code=404, detail=f"Unknown concern: {concern_id}")
    return page


@router.get("/symptom_explainer/{symptom_keyword}")
async def symptom_explainer(symptom_keyword: str):
    page = assemble_symptom_explainer(symptom_keyword)
    if not page:
        raise HTTPException(status_code=404, detail=f"No explainer for: {symptom_keyword}")
    return page


@router.get("/event_guides")
async def event_guides(city: str = Query(...)):
    return {"city": city, "guides": assemble_event_guides(city)}


@router.get("/explore")
async def explore_lane(
    city: str = Query(...),
    concern_id: str | None = Query(None),
    user_id: str | None = Query(None),
    raw_uvi: float | None = Query(None, ge=0),
    raw_aqi: int | None = Query(None, ge=0),
    raw_rh: float | None = Query(None, ge=0, le=100),
    raw_temp: float | None = Query(None),
    auth_user: dict | None = Depends(hlhp_optional_authenticated_user),
):
    resolved_user_id = resolve_optional_personalization_user_id(auth_user, user_id)
    selected = await fetch_selected_symptoms(resolved_user_id) if resolved_user_id else set()
    profile = await load_user_profile(resolved_user_id) if resolved_user_id else None
    bands = None
    if raw_uvi is not None and raw_aqi is not None and raw_rh is not None and raw_temp is not None:
        env = EnvironmentalData(
            uv_index=raw_uvi,
            temperature_c=raw_temp,
            aqi=raw_aqi,
            humidity_pct=raw_rh,
            location_name=city,
        )
        bands = bucketize_environment(env)
    payload = assemble_explore(
        city,
        concern_id,
        selected_symptoms=selected,
        user_id=resolved_user_id,
        profile=profile,
        bands=bands,
    )
    pool = await fetch_knowledge_feed_pool()
    payload["knowledge_feed"] = rank_knowledge_feed_posts(
        pool,
        concern_id=payload.get("concern_id"),
        bands=bands,
        when=datetime.now().astimezone(),
        user_id=resolved_user_id,
        profile=profile,
        limit=4,
    )
    return payload


@router.get("/week_ahead")
async def week_ahead(
    city: str = Query(...),
    concern_id: str | None = Query(None),
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    raw_uvi: float = Query(5.0, ge=0),
    raw_aqi: int = Query(50, ge=0),
    raw_rh: float = Query(50.0, ge=0, le=100),
    raw_temp: float = Query(25.0),
    days: int = Query(3, ge=1, le=3),
):
    if latitude is not None and longitude is not None:
        profile = None
        return await assemble_plan_week(
            latitude=latitude,
            longitude=longitude,
            city=city,
            concern_id=concern_id,
            days=days,
        )

    req = ScanRequest(
        user_id=None,
        city=city,
        local_time=datetime.now().astimezone(),
        raw_uvi=raw_uvi,
        raw_aqi=raw_aqi,
        raw_rh=raw_rh,
        raw_temp=raw_temp,
    )
    env = await resolve_environment(req)
    week_days = assemble_week_ahead(base_env=env, concern_id=concern_id, mood_today="", days=days)
    return {
        "city": city,
        "concern_id": concern_id,
        "days": week_days,
        "forecast_source": "synthetic",
        "workbook_version": get_scenario_store().workbook_version,
    }


@router.get("/plan_week")
async def plan_week_lane(
    city: str = Query(...),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    concern_id: str | None = Query(None),
    user_id: str | None = Query(None),
    days: int = Query(3, ge=1, le=3),
    auth_user: dict | None = Depends(hlhp_optional_authenticated_user),
):
    resolved_user_id = resolve_optional_personalization_user_id(auth_user, user_id)
    profile = await load_user_profile(resolved_user_id) if resolved_user_id else None
    from app.hlhp.services.concern_resolver import resolve_concern_id

    resolved = resolve_concern_id(profile=profile, client_concern_id=concern_id)
    return await assemble_plan_week(
        latitude=latitude,
        longitude=longitude,
        city=city,
        concern_id=resolved,
        profile=profile,
        days=days,
    )


@router.get("/sfi_timeline")
async def sfi_timeline_lane(
    city: str = Query(...),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    user_id: str | None = Query(None),
    days_back: int = Query(3, ge=0, le=7),
    days_ahead: int = Query(3, ge=0, le=7),
    auth_user: dict | None = Depends(hlhp_optional_authenticated_user),
):
    resolved_user_id = resolve_optional_personalization_user_id(auth_user, user_id)
    profile = await load_user_profile(resolved_user_id) if resolved_user_id else None
    return await assemble_sfi_timeline(
        latitude=latitude,
        longitude=longitude,
        city=city,
        user_id=resolved_user_id,
        profile=profile,
        days_back=days_back,
        days_ahead=days_ahead,
    )


@router.get("/history")
async def history_lane(
    user_id: str = Query(...),
    days: int = Query(30, ge=1, le=30),
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = verify_client_user_id(user, user_id)
    return await assemble_history(uid, days=days)


@router.get("/patterns")
async def patterns_lane(
    user_id: str = Query(...),
    days: int = Query(30, ge=1, le=30),
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = verify_client_user_id(user, user_id)
    return await assemble_patterns(uid, days=days)


@router.get("/catchup")
async def catchup_lane(
    user_id: str = Query(...),
    days: int = Query(30, ge=1, le=30),
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = verify_client_user_id(user, user_id)
    return await assemble_catchup(uid, days=days)


@router.get("/log/status", response_model=FeelingLogStatus)
async def feeling_log_status_lane(
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
) -> FeelingLogStatus:
    uid = verify_client_user_id(user, user_id)
    status = await fetch_feeling_log_status(uid)
    return FeelingLogStatus(**status)


@router.post("/log", response_model=UserLogResponse)
async def user_log_lane(
    body: UserLogRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> UserLogResponse:
    uid = verify_client_user_id(user, body.user_id)
    if uid != body.user_id:
        body = body.model_copy(update={"user_id": uid})
    try:
        return await run_user_log(body)
    except HlhpStoreError as exc:
        http_503_for_store_error(exc)


@router.get("/streak", response_model=StreakResponse)
async def streak_lane(
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
) -> StreakResponse:
    uid = verify_client_user_id(user, user_id)
    return await assemble_streak(uid)


@router.get("/weekly-card", response_model=WeeklyCardResponse)
async def weekly_card_lane(
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
) -> WeeklyCardResponse:
    uid = verify_client_user_id(user, user_id)
    return await assemble_weekly_card(uid)


@router.get("/learn", response_model=LearnResponse)
async def learn_lane(
    user_id: str = Query(...),
    city: str | None = Query(None),
    concern_id: str | None = Query(None),
    raw_uvi: float | None = Query(None, ge=0),
    raw_aqi: int | None = Query(None, ge=0),
    raw_rh: float | None = Query(None, ge=0, le=100),
    raw_temp: float | None = Query(None),
    user: dict = Depends(hlhp_authenticated_user),
) -> LearnResponse:
    uid = verify_client_user_id(user, user_id)
    bands = None
    if raw_uvi is not None and raw_aqi is not None and raw_rh is not None and raw_temp is not None:
        env = EnvironmentalData(
            uv_index=raw_uvi,
            temperature_c=raw_temp,
            aqi=raw_aqi,
            humidity_pct=raw_rh,
            location_name=city or "",
        )
        bands = bucketize_environment(env)
    return await assemble_learn(
        uid,
        city=city,
        concern_id=concern_id,
        bands=bands,
    )


@router.post("/consent", response_model=ConsentResponse)
async def record_consent(
    body: ConsentRequest,
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = verify_client_user_id(user, body.user_id)
    if uid != body.user_id:
        body = body.model_copy(update={"user_id": uid})
    try:
        return await upsert_consent(body)
    except HlhpStoreError as exc:
        http_503_for_store_error(exc)


@router.get("/consent", response_model=ConsentStatusResponse)
async def read_consent(
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = verify_client_user_id(user, user_id)
    return await get_consent(uid)
