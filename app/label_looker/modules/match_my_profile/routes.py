from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Body, Depends

from app.label_looker.modules.match_my_profile import service
from app.label_looker.modules.shared.responses import api_success


def build_router(auth_user: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> APIRouter:
    r = APIRouter()

    @r.get("/product/{product_id}/expected-benefit-options")
    async def expected_benefit_options_match(product_id: str, user: dict[str, Any] = Depends(auth_user)):
        _ = user
        from app.label_looker.services.expected_benefit_options import get_expected_benefit_options

        return api_success(await get_expected_benefit_options(product_id=product_id), message="Success")

    @r.post("/score")
    async def profile_match_score(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await service.score_product(user=user, body=body)
        return api_success(data, message="Success")

    @r.post("/scan/{scan_id}/feedback")
    async def profile_match_feedback(
        scan_id: str,
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await service.submit_feedback(user=user, scan_id=scan_id, body=body)
        return api_success(data, message="Feedback added successfully")

    @r.get("/profile")
    async def profile_match_get_profile(
        productId: str | None = None,
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await service.get_profile(user=user, product_id=productId)
        return api_success(data, message="Success")

    @r.patch("/profile")
    async def profile_match_patch_profile(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await service.patch_profile(user=user, body=body)
        return api_success(data, message="Success")

    return r

