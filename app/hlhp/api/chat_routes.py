"""HLHP seeker chat — /v2/chats/*."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.hlhp.api.deps_auth import hlhp_authenticated_user, verify_client_user_id
from app.hlhp.api.hub_errors import raise_for_hub_error
from app.hlhp.core.bus_client import HlhpHubError
from app.hlhp.models.hlhp_bus import HlhpChatMessageRequest, HlhpTypingRequest
from app.hlhp.services.chat_service import (
    get_chat_state,
    mark_seeker_read,
    post_seeker_message,
    post_seeker_typing,
)

router = APIRouter(prefix="/v2", tags=["HLHP Chat"])


def _bearer_from_user(user: dict[str, Any]) -> str | None:
    token = user.get("_label_looker_access_token")
    return str(token) if token else None


@router.get("/chats")
async def read_chats(
    user_id: str = Query(...),
    doctor_id: str | None = Query(None, alias="doctorId"),
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, user_id)
    try:
        return await get_chat_state(uid, doctor_id, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/chats/messages")
async def send_message(
    body: HlhpChatMessageRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await post_seeker_message(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/chats/read")
async def mark_read(
    user_id: str = Query(...),
    doctor_id: str | None = Query(None, alias="doctorId"),
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, user_id)
    try:
        return await mark_seeker_read(uid, doctor_id=doctor_id, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)


@router.post("/chats/typing")
async def typing_indicator(
    body: HlhpTypingRequest,
    user: dict = Depends(hlhp_authenticated_user),
) -> dict[str, Any]:
    uid = verify_client_user_id(user, body.user_id)
    try:
        return await post_seeker_typing(uid, body, bearer_token=_bearer_from_user(user))
    except HlhpHubError as exc:
        raise_for_hub_error(exc)
