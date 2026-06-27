"""HLHP composition layer API routes (UI spec §10)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

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
from app.hlhp.evidence.loader import get_evidence_store
from app.hlhp.models.history import ConsentRequest, ConsentResponse, ConsentStatusResponse
from app.hlhp.models.scan import ScanRequest
from app.hlhp.services.consent_store import get_consent, upsert_consent
from app.hlhp.coach.state_store import fetch_selected_symptoms
from app.hlhp.services.history_service import assemble_catchup, assemble_history
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
):
    selected = await fetch_selected_symptoms(user_id) if user_id else set()
    profile = await load_user_profile(user_id) if user_id else None
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
        user_id=user_id,
        profile=profile,
        bands=bands,
    )
    pool = await fetch_knowledge_feed_pool()
    payload["knowledge_feed"] = rank_knowledge_feed_posts(
        pool,
        concern_id=payload.get("concern_id"),
        bands=bands,
        when=datetime.now().astimezone(),
        user_id=user_id,
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
        "workbook_version": get_evidence_store().workbook_version,
    }


@router.get("/plan_week")
async def plan_week_lane(
    city: str = Query(...),
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    concern_id: str | None = Query(None),
    user_id: str | None = Query(None),
    days: int = Query(3, ge=1, le=3),
):
    profile = await load_user_profile(user_id) if user_id else None
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
):
    profile = await load_user_profile(user_id) if user_id else None
    return await assemble_sfi_timeline(
        latitude=latitude,
        longitude=longitude,
        city=city,
        user_id=user_id,
        profile=profile,
        days_back=days_back,
        days_ahead=days_ahead,
    )


@router.get("/history")
async def history_lane(user_id: str = Query(...), days: int = Query(15, ge=1, le=15)):
    return await assemble_history(user_id, days=days)


@router.get("/catchup")
async def catchup_lane(user_id: str = Query(...), days: int = Query(15, ge=1, le=15)):
    return await assemble_catchup(user_id, days=days)


@router.post("/consent", response_model=ConsentResponse)
async def record_consent(body: ConsentRequest):
    return await upsert_consent(body)


@router.get("/consent", response_model=ConsentStatusResponse)
async def read_consent(user_id: str = Query(...)):
    return await get_consent(user_id)
