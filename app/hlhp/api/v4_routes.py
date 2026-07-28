"""HLHP V4 prototype REST surface — /v2/* contract from July 2026 handoff."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.hlhp.api.deps_auth import (
    hlhp_authenticated_user,
    hlhp_optional_authenticated_user,
    resolve_optional_personalization_user_id,
    user_id_from_auth,
    verify_client_user_id,
)
from app.hlhp.api.store_http import http_503_for_store_error
from app.hlhp.db_errors import HlhpStoreError
from app.hlhp.models.patterns_v2 import PatternsPayloadV2
from app.hlhp.models.v4_api import (
    V4LearnResponse,
    V4LogRequest,
    V4LogResponse,
    V4RecapResponse,
    V4ShareResponse,
    V4TodayResponse,
)
from app.hlhp.services.patterns_engine_service import recompute_patterns_for_user
from app.hlhp.services.city_chart_service import build_city_chart
from app.hlhp.services.selfie_service import (
    delete_daily_selfie,
    get_selfie_for_date,
    list_selfies,
    read_selfie_bytes,
    upsert_daily_selfie,
)
from app.hlhp.services.v4_api_service import (
    assemble_learn_v4,
    assemble_recap,
    assemble_share,
    assemble_today,
    run_v4_log,
)

router = APIRouter(prefix="/v2", tags=["HLHP V4 — Prototype API"])


@router.get("/cities")
async def v4_cities(
    city: str = Query("Pune", description="Your city — flags the YOU row"),
    surge: bool = Query(False, description="Apply surge drill to your city"),
):
    """City SFI leaderboard from WeatherAPI slot averages (11 fixed cities + optional YOU)."""
    return await build_city_chart(you_city=city, surge=surge)


@router.post("/selfies")
async def upload_selfie(
    file: UploadFile = File(...),
    date: str = Form(..., description="Local calendar day YYYY-MM-DD"),
    user: dict = Depends(hlhp_authenticated_user),
):
    """Upsert today's selfie — one per user+day under s3://…/HLHP-LOG/{user}/{date}_{HHMMSS}.jpg."""
    uid = user_id_from_auth(user)
    return await upsert_daily_selfie(uid, date, file)


@router.get("/selfies/media")
async def get_selfie_media(
    date: str = Query(..., description="Local calendar day YYYY-MM-DD"),
    user: dict = Depends(hlhp_authenticated_user),
):
    """Serve the day's selfie JPEG (local cache, rehydrated from S3 after deploy)."""
    uid = user_id_from_auth(user)
    data = await read_selfie_bytes(uid, date)
    if not data:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "No selfie for that day."},
        )
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.get("/selfies")
async def get_selfies(
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
    date: str | None = Query(None, description="Single day YYYY-MM-DD"),
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = user_id_from_auth(user)
    if date:
        row = await get_selfie_for_date(uid, date)
        return {"selfies": [row] if row else []}
    rows = await list_selfies(uid, date_from=date_from, date_to=date_to)
    return {"selfies": rows}


@router.delete("/selfies")
async def remove_selfie(
    date: str = Query(..., description="Local calendar day YYYY-MM-DD"),
    user: dict = Depends(hlhp_authenticated_user),
):
    uid = user_id_from_auth(user)
    return await delete_daily_selfie(uid, date)


@router.get("/today", response_model=V4TodayResponse)
async def v4_today(
    city: str = Query(...),
    local_time: datetime | None = None,
    latitude: float | None = Query(None, ge=-90, le=90),
    longitude: float | None = Query(None, ge=-180, le=180),
    raw_uvi: float | None = Query(None, ge=0),
    raw_aqi: int | None = Query(None, ge=0),
    raw_rh: float | None = Query(None, ge=0, le=100),
    raw_temp: float | None = Query(None),
    force_surge: bool = Query(False),
    user_id: str | None = Query(None),
    auth_user: dict | None = Depends(hlhp_optional_authenticated_user),
) -> V4TodayResponse:
    resolved_uid = resolve_optional_personalization_user_id(auth_user, user_id)
    when = local_time or datetime.now().astimezone()
    return await assemble_today(
        user_id=resolved_uid,
        city=city,
        local_time=when,
        latitude=latitude,
        longitude=longitude,
        raw_uvi=raw_uvi,
        raw_aqi=raw_aqi,
        raw_rh=raw_rh,
        raw_temp=raw_temp,
        force_surge=force_surge,
        auth_user=auth_user,
    )


@router.post("/logs", response_model=V4LogResponse)
async def v4_logs(
    body: V4LogRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> V4LogResponse:
    uid = verify_client_user_id(user, body.user_id)
    if uid != body.user_id:
        body = body.model_copy(update={"user_id": uid})
    try:
        return await run_v4_log(body)
    except HlhpStoreError as exc:
        http_503_for_store_error(exc)


@router.get("/streak")
async def v4_streak(
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
):
    from app.hlhp.services.engagement_service import assemble_streak

    uid = verify_client_user_id(user, user_id)
    streak = await assemble_streak(uid)
    return {
        "current_streak": streak.current_streak,
        "longest_streak": streak.longest_streak,
        "last_7_days": [
            {"date": d.date, "logged": d.done} for d in streak.week_grid
        ],
        "next_milestone": 7 if streak.current_streak < 7 else 30,
        "days_to_next_milestone": streak.days_to_next_badge,
    }


@router.get("/recap", response_model=V4RecapResponse)
async def v4_recap(
    month: str = Query(..., description="YYYY-MM"),
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
) -> V4RecapResponse:
    uid = verify_client_user_id(user, user_id)
    return await assemble_recap(uid, month)


@router.get("/patterns", response_model=PatternsPayloadV2)
async def v4_patterns(
    user_id: str = Query(...),
    user: dict = Depends(hlhp_authenticated_user),
) -> PatternsPayloadV2:
    uid = verify_client_user_id(user, user_id)
    payload = await recompute_patterns_for_user(uid)
    return PatternsPayloadV2(**payload)


@router.get("/share", response_model=V4ShareResponse)
async def v4_share(
    user_id: str = Query(...),
    city: str = Query(""),
    user: dict = Depends(hlhp_authenticated_user),
) -> V4ShareResponse:
    uid = verify_client_user_id(user, user_id)
    return await assemble_share(uid, city=city)


@router.get("/learn", response_model=V4LearnResponse)
async def v4_learn(
    user_id: str = Query(...),
    city: str | None = Query(None),
    concern_id: str | None = Query(None),
    raw_uvi: float | None = Query(None, ge=0),
    raw_aqi: int | None = Query(None, ge=0),
    raw_rh: float | None = Query(None, ge=0, le=100),
    raw_temp: float | None = Query(None),
    user: dict = Depends(hlhp_authenticated_user),
) -> V4LearnResponse:
    uid = verify_client_user_id(user, user_id)
    bands = None
    if raw_uvi is not None and raw_aqi is not None and raw_rh is not None and raw_temp is not None:
        from app.hlhp.core.bands import bucketize_environment
        from app.hlhp.models.environmental import EnvironmentalData

        env = EnvironmentalData(
            uv_index=raw_uvi,
            temperature_c=raw_temp,
            aqi=raw_aqi,
            humidity_pct=raw_rh,
            location_name=city or "",
        )
        bands = bucketize_environment(env)
    return await assemble_learn_v4(uid, city=city, concern_id=concern_id, bands=bands)
