from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile

from app.label_looker.modules.product_analysis import service
from app.label_looker.modules.product_analysis import admin_service
from app.label_looker.modules.shared.auth import authorize_scan_overview_view, panel_auth_only
from app.label_looker.modules.shared.responses import api_success
from app.label_looker.upload_utils import save_scan_image, validate_upload


def build_scanner_router(auth_user: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> APIRouter:
    r = APIRouter()

    @r.post("/image-conversion")
    async def image_conversion(image: UploadFile = File(...), user: dict[str, Any] = Depends(auth_user)):
        raw = await image.read()
        ct = validate_upload(image.content_type, len(raw))
        base = save_scan_image(image.filename, ct, raw)
        data = await service.scan_image_to_text(user=user, image_bytes=raw, content_type=ct, image_basename=base)
        return api_success(data, message="Ingredient list")

    @r.post("/analyze-product")
    async def analyze_product(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(auth_user)):
        return api_success(await service.ingredient_analysis(body=body, user=user), message="Success")

    @r.post("/ingredient")
    async def ingredient_detail(name: str | None = Query(None), user: dict[str, Any] = Depends(auth_user)):
        _ = user
        return api_success(await service.get_ingredient_detail_response(name=name), message="Success")

    @r.put("/feedback")
    async def feedback(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(auth_user)):
        _ = user
        await service.put_feedback(body=body)
        return api_success({}, message="Feedback added successfully")

    @r.get("/scan-left")
    async def scan_left(user: dict[str, Any] = Depends(auth_user)):
        return api_success(await service.number_of_scan_left(user=user), message="Success")

    return r


def build_public_text_router(
    auth_optional: Callable[..., Coroutine[Any, Any, dict[str, Any] | None]],
    auth_required: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
) -> APIRouter:
    r = APIRouter()

    @r.post("/analyze-product/text")
    async def analyze_product_text(body: dict[str, Any] = Body(...), user: dict[str, Any] | None = Depends(auth_optional)):
        return api_success(await service.ingredient_analysis_from_text(body=body, user=user), message="Success")

    @r.post("/profile-validation/submit")
    async def profile_validation_submit(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(auth_required)):
        return api_success(await service.submit_profile_validation(body=body, user=user), message="Success")

    @r.post("/profile-validation/status")
    async def profile_validation_status(body: dict[str, Any] = Body(...), user: dict[str, Any] = Depends(auth_required)):
        return api_success(await service.profile_validation_status(body=body, user=user), message="Success")

    @r.get("/user/analysis/{scan_id}")
    async def user_analysis_by_id(scan_id: str, user: dict[str, Any] | None = Depends(auth_optional)):
        return api_success(await service.user_scan_by_id(scan_id=scan_id, user=user), message="Success")

    @r.get("/user/analysis")
    async def user_analysis_list(
        skip: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        user: dict[str, Any] | None = Depends(auth_optional),
    ):
        return api_success(await service.user_scan_list(user=user, skip=skip, limit=limit), message="Success")

    return r


def build_admin_router() -> APIRouter:
    a = APIRouter()

    @a.get("/analysis/list")
    async def analysis_list(ctx=Depends(authorize_scan_overview_view), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)):
        _ = ctx
        return api_success(await admin_service.analysis_list(skip=skip, limit=limit), message="Success")

    @a.get("/analysis/{scan_id}")
    async def analysis_one(scan_id: str, ctx=Depends(authorize_scan_overview_view)):
        _ = ctx
        return api_success(await admin_service.analysis_by_id(scan_id), message="Success")

    @a.get("/analytics")
    async def analytics(ctx=Depends(panel_auth_only)):
        _ = ctx
        return api_success(await admin_service.analytics_summary(), message="Success")

    @a.get("/user/total-scan")
    async def total_scan(ctx=Depends(authorize_scan_overview_view)):
        _ = ctx
        return api_success(await admin_service.user_total_scan(), message="Success")

    @a.get("/rating-count")
    async def rating_count(ctx=Depends(authorize_scan_overview_view)):
        _ = ctx
        return api_success(await admin_service.rating_counts(), message="Success")

    return a

