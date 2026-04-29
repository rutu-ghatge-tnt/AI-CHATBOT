from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile

from app.label_looker import admin_service, analysis_service, ingredient_service, scan_service
from app.label_looker.deps_auth import (
    authorize_scan_overview_view,
    panel_auth_only,
)
from app.label_looker.responses import api_success
from app.label_looker.upload_utils import save_scan_image, validate_upload


def _scanner_routes(auth_user: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> APIRouter:
    r = APIRouter()

    @r.post("/image-conversion")
    async def image_conversion(
        image: UploadFile = File(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        raw = await image.read()
        ct = validate_upload(image.content_type, len(raw))
        base = save_scan_image(image.filename, ct, raw)
        data = await scan_service.scan_image_to_text(
            user=user,
            image_bytes=raw,
            content_type=ct,
            image_basename=base,
        )
        return api_success(data, message="Ingredient list")

    @r.post("/ingredients-analysis")
    async def ingredients_analysis(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await analysis_service.ingredient_analysis(body=body, user=user)
        return api_success(data, message="Success")

    @r.post("/ingredient")
    async def ingredient_detail(
        name: str | None = Query(None),
        user: dict[str, Any] = Depends(auth_user),
    ):
        _ = user
        data = await ingredient_service.get_ingredient_detail_response(name=name)
        return api_success(data, message="Success")

    @r.put("/feedback")
    async def feedback(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        _ = user
        await analysis_service.put_feedback(body=body)
        return api_success({}, message="Feedback added successfully")

    @r.get("/scan-left")
    async def scan_left(user: dict[str, Any] = Depends(auth_user)):
        data = await scan_service.number_of_scan_left(user=user)
        return api_success(data, message="Success")

    return r


def admin_router() -> APIRouter:
    a = APIRouter()

    @a.get("/analysis/list")
    async def analysis_list(
        ctx=Depends(authorize_scan_overview_view),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
    ):
        _ = ctx
        rows = await admin_service.analysis_list(skip=skip, limit=limit)
        return api_success(rows, message="Success")

    @a.get("/analysis/{scan_id}")
    async def analysis_one(scan_id: str, ctx=Depends(authorize_scan_overview_view)):
        _ = ctx
        doc = await admin_service.analysis_by_id(scan_id)
        return api_success(doc, message="Success")

    @a.get("/analytics")
    async def analytics(ctx=Depends(panel_auth_only)):
        _ = ctx
        data = await admin_service.analytics_summary()
        return api_success(data, message="Success")

    @a.get("/user/total-scan")
    async def total_scan(ctx=Depends(authorize_scan_overview_view)):
        _ = ctx
        data = await admin_service.user_total_scan()
        return api_success(data, message="Success")

    @a.get("/rating-count")
    async def rating_count(ctx=Depends(authorize_scan_overview_view)):
        _ = ctx
        data = await admin_service.rating_counts()
        return api_success(data, message="Success")

    return a


def public_text_routes(
    auth_optional: Callable[..., Coroutine[Any, Any, dict[str, Any] | None]],
    auth_required: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
) -> APIRouter:
    r = APIRouter()

    @r.post("/text-ingredients-analysis")
    async def text_ingredients_analysis(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] | None = Depends(auth_optional),
    ):
        data = await analysis_service.ingredient_analysis_from_text(body=body, user=user)
        return api_success(data, message="Success")

    @r.post("/profile-validation/submit")
    async def profile_validation_submit(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_required),
    ):
        data = await analysis_service.submit_profile_validation(body=body, user=user)
        return api_success(data, message="Success")

    @r.post("/profile-validation/status")
    async def profile_validation_status(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_required),
    ):
        data = await analysis_service.profile_validation_status(body=body, user=user)
        return api_success(data, message="Success")

    @r.get("/user/analysis/{scan_id}")
    async def user_analysis_by_id(
        scan_id: str,
        user: dict[str, Any] = Depends(auth_required),
    ):
        data = await analysis_service.user_scan_by_id(scan_id=scan_id, user=user)
        return api_success(data, message="Success")

    @r.get("/user/analysis")
    async def user_analysis_list(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        user: dict[str, Any] = Depends(auth_required),
    ):
        data = await analysis_service.user_scan_list(user=user, skip=skip, limit=limit)
        return api_success(data, message="Success")

    return r
