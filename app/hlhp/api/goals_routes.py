"""HLHP goals + profile — proxy Node `/api/v1/hlhp/goals` (seeker JWT)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.hlhp.api.deps_auth import hlhp_authenticated_user, verify_client_user_id
from app.hlhp.api.hub_errors import raise_for_hub_error
from app.hlhp.core.bus_client import HlhpHubError
from app.hlhp.models.hlhp_bus import HlhpGoalCreateRequest, HlhpProfileUpdateRequest
from app.hlhp.services.goal_service import (
    HlhpGoalsError,
    assign_doctor,
    get_goals,
    setup_goal,
    update_profile,
)

router = APIRouter(prefix="/v2", tags=["HLHP Goals"])


def _bearer_from_user(user: dict[str, Any]) -> str | None:
    token = user.get("_label_looker_access_token")
    return str(token) if token else None


def _raise_goals(exc: HlhpGoalsError) -> None:
    # Reuse hub error mapper shape for consistent FE envelopes.
    raise_for_hub_error(HlhpHubError(exc.status_code, exc.message, exc.detail))


class HlhpAssignDoctorRequest(BaseModel):
    user_id: str | None = None
    doctor_id: str = Field(..., alias="doctorId", min_length=1)

    model_config = {"populate_by_name": True}


@router.get("/goals")
async def read_goals(
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    try:
        data = await get_goals(bearer_token=_bearer_from_user(user))
    except HlhpGoalsError as exc:
        _raise_goals(exc)
    return data


@router.post("/goals")
async def create_goal(
    body: HlhpGoalCreateRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        payload = await setup_goal(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpGoalsError as exc:
        _raise_goals(exc)
    return {"ok": True, "goal": payload}


@router.patch("/goals/doctor")
async def patch_goal_doctor(
    body: HlhpAssignDoctorRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        payload = await assign_doctor(
            uid, body.doctor_id, bearer_token=_bearer_from_user(user)
        )
    except HlhpGoalsError as exc:
        _raise_goals(exc)
    return {"ok": True, **(payload if isinstance(payload, dict) else {"goal": payload})}


@router.post("/profile")
async def merge_profile(
    body: HlhpProfileUpdateRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        payload = await update_profile(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpGoalsError as exc:
        _raise_goals(exc)
    return {"ok": True, "profile": payload}
