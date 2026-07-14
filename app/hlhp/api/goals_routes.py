"""HLHP goals + profile — /v2/goals, /v2/profile."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.hlhp.api.deps_auth import hlhp_authenticated_user, user_id_from_auth, verify_client_user_id
from app.hlhp.api.hub_errors import raise_for_hub_error
from app.hlhp.core.bus_client import HlhpHubError
from app.hlhp.models.hlhp_bus import HlhpGoalCreateRequest, HlhpProfileUpdateRequest
from app.hlhp.services.goal_service import setup_goal, update_profile

router = APIRouter(prefix="/v2", tags=["HLHP Goals"])


def _bearer_from_user(user: dict[str, Any]) -> str | None:
    token = user.get("_label_looker_access_token")
    return str(token) if token else None


@router.post("/goals")
async def create_goal(
    body: HlhpGoalCreateRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        payload = await setup_goal(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)
    return {"ok": True, "goal": payload}


@router.post("/profile")
async def merge_profile(
    body: HlhpProfileUpdateRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        payload = await update_profile(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)
    return {"ok": True, "profile": payload}
