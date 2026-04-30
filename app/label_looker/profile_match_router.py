from __future__ import annotations

from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Body, Depends

from app.label_looker import profile_match_service
from app.label_looker.responses import api_success


def profile_match_routes(auth_user: Callable[..., Coroutine[Any, Any, dict[str, Any]]]) -> APIRouter:
    r = APIRouter()

    @r.post("/score")
    async def profile_match_score(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await profile_match_service.score_product(user=user, body=body)
        return api_success(data, message="Success")

    @r.post("/scan/{scan_id}/feedback")
    async def profile_match_feedback(
        scan_id: str,
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await profile_match_service.submit_feedback(user=user, scan_id=scan_id, body=body)
        return api_success(data, message="Feedback added successfully")

    @r.get("/profile")
    async def profile_match_get_profile(user: dict[str, Any] = Depends(auth_user)):
        data = await profile_match_service.get_profile(user=user)
        return api_success(data, message="Success")

    @r.patch("/profile")
    async def profile_match_patch_profile(
        body: dict[str, Any] = Body(...),
        user: dict[str, Any] = Depends(auth_user),
    ):
        data = await profile_match_service.patch_profile(user=user, body=body)
        return api_success(data, message="Success")

    return r
