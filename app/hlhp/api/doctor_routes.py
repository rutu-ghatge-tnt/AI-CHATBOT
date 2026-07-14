"""HLHP doctor panel — /hlhp/doctor/*."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.hlhp.api.deps_auth import (
    hlhp_doctor_authenticated_user,
    user_id_from_auth,
)
from app.hlhp.api.hub_errors import raise_for_hub_error
from app.hlhp.core.bus_client import HlhpHubError
from app.hlhp.models.hlhp_bus import (
    HlhpDoctorMessageRequest,
    HlhpDoctorOnboardComplete,
    HlhpDoctorSubscriptionUpdate,
)
from app.hlhp.services.doctor_panel_service import (
    accept_seeker,
    approve_plan,
    complete_onboarding,
    get_crt_stats,
    get_panel_for_doctor,
    post_doctor_message,
    set_subscription_fee,
)

router = APIRouter(prefix="/hlhp/doctor", tags=["HLHP Doctor Panel"])


def _bearer_from_user(user: dict[str, Any]) -> str | None:
    token = user.get("_label_looker_access_token")
    return str(token) if token else None


def _display_name(user: dict[str, Any]) -> str:
    first = str(user.get("firstName") or user.get("first_name") or "").strip()
    last = str(user.get("lastName") or user.get("last_name") or "").strip()
    name = f"{first} {last}".strip()
    return name or str(user.get("name") or "Doctor")


@router.get("/panel")
async def panel(
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    try:
        return await get_panel_for_doctor(doctor_id, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/panel/{seeker_id}/accept")
async def panel_accept(
    seeker_id: str,
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    try:
        return await accept_seeker(
            doctor_id,
            seeker_id,
            doctor_name=_display_name(user),
            bearer_token=_bearer_from_user(user),
        )
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/plans/{seeker_id}/approve")
async def plan_approve(
    seeker_id: str,
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    try:
        return await approve_plan(
            doctor_id,
            seeker_id,
            doctor_name=_display_name(user),
            bearer_token=_bearer_from_user(user),
        )
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.put("/subscription")
async def subscription_fee(
    body: HlhpDoctorSubscriptionUpdate,
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    try:
        return await set_subscription_fee(
            doctor_id,
            body,
            doctor_name=_display_name(user),
            bearer_token=_bearer_from_user(user),
        )
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/chats/{seeker_id}/messages")
async def doctor_send_message(
    seeker_id: str,
    body: HlhpDoctorMessageRequest,
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    try:
        return await post_doctor_message(
            doctor_id,
            seeker_id,
            body,
            bearer_token=_bearer_from_user(user),
        )
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.get("/crt")
async def crt_stats(
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    try:
        return await get_crt_stats(doctor_id, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/onboarding/complete")
async def onboarding_complete(
    body: HlhpDoctorOnboardComplete,
    user: dict = Depends(hlhp_doctor_authenticated_user),
) -> dict[str, Any]:
    doctor_id = user_id_from_auth(user)
    if not body.name:
        body = body.model_copy(update={"name": _display_name(user)})
    try:
        return await complete_onboarding(
            doctor_id,
            body,
            bearer_token=_bearer_from_user(user),
        )
    except HlhpHubError as exc:
        raise_for_hub_error(exc)
