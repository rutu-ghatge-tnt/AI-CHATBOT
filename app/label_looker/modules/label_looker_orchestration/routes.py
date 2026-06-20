from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Body, Depends, Query

from app.label_looker.modules.label_looker_orchestration import service_impl
from app.label_looker.modules.shared.responses import api_success


def build_label_looker_router(auth_user: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> APIRouter:
    r = APIRouter()

    @r.get("/labellooker/scan")
    async def labellooker_scan_lookup(
        productId: str = Query(..., alias="productId"),
        user: dict[str, Any] = Depends(auth_user),
    ):
        return api_success(
            await service_impl.get_product_scan_lookup(user=user, product_id=productId),
            message="Success",
        )

    @r.post("/match-my-profile")
    async def post_match_my_profile(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        return api_success(
            await service_impl.post_match_my_profile(user=user, body=body),
            message="Success",
        )

    @r.get("/match-my-profile/{user_scan_id}")
    async def get_match_by_user_scan_id(
        user_scan_id: str,
        user: dict[str, Any] = Depends(auth_user),
    ):
        return api_success(
            await service_impl.get_match_by_user_scan_id(user=user, user_scan_id=user_scan_id),
            message="Success",
        )

    @r.get("/text/{scan_id}")
    async def get_text_analysis(
        scan_id: str,
        user: dict[str, Any] = Depends(auth_user),
    ):
        return api_success(
            await service_impl.get_text_analysis(user=user, scan_id=scan_id),
            message="Success",
        )

    return r
