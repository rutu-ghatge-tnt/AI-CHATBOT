"""HLHP goals — proxy to Node REST `/api/v1/hlhp/goals`.

Node owns goal persistence and publishes `hlhp_goal_setup_v1` after writes.
Python must NOT hub-write goal / accept / approval keys.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.core.hub_state import unwrap_envelope
from app.hlhp.models.hlhp_bus import HlhpGoalCreateRequest, HlhpProfileUpdateRequest

logger = logging.getLogger(__name__)


class HlhpGoalsError(Exception):
    def __init__(self, status_code: int, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.detail = detail


def _auth_headers(bearer_token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return headers


def _goals_base() -> str:
    settings = get_hlhp_settings()
    if not settings.node_configured:
        raise HlhpGoalsError(
            503,
            "HLHP goals are not configured (set HLHP_NODE_API_URL or SKIN_BB_BASE_URL)",
        )
    return f"{settings.node_api_url}/api/v1/hlhp/goals"


async def _node_request(
    method: str,
    path: str = "",
    *,
    json_body: dict[str, Any] | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    url = _goals_base() + path
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(
            method,
            url,
            json=json_body,
            headers=_auth_headers(bearer_token),
        )

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        logger.warning("HLHP goals %s %s failed %s: %s", method, path or "/", response.status_code, detail)
        msg = "Goals request failed"
        if isinstance(detail, dict) and detail.get("message"):
            msg = str(detail["message"])
        raise HlhpGoalsError(response.status_code, msg, detail)

    try:
        raw = response.json()
    except Exception:
        return {"ok": True}

    data = unwrap_envelope(raw)
    if isinstance(data, dict):
        return data
    return {"ok": True, "raw": data}


def _seeker_goal_body(body: HlhpGoalCreateRequest) -> dict[str, Any]:
    """Node seeker contract — no seekerId, ts, status, or assignedDoctorId."""
    payload: dict[str, Any] = {
        "goalName": body.goal_name,
        "goalType": body.goal_type or "wedding",
        "days": int(body.days),
        "concern": body.concern or body.goal_focus or "Skin concern",
    }
    if body.goal_focus:
        payload["goalFocus"] = body.goal_focus
    if body.brief:
        payload["brief"] = body.brief
    return payload


async def get_goals(*, bearer_token: str | None = None) -> dict[str, Any]:
    return await _node_request("GET", bearer_token=bearer_token)


async def setup_goal(
    user_id: str,
    body: HlhpGoalCreateRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Create/upsert goal via Node REST. Identity comes from JWT — user_id unused for body."""
    _ = user_id
    data = await _node_request(
        "POST",
        json_body=_seeker_goal_body(body),
        bearer_token=bearer_token,
    )
    # Optional: assign doctor in the same call path if legacy clients still send it.
    doctor_id = (body.assigned_doctor_id or "").strip()
    if doctor_id:
        data = await assign_doctor(user_id, doctor_id, bearer_token=bearer_token)
    return data.get("goal") if isinstance(data.get("goal"), dict) else data


async def assign_doctor(
    user_id: str,
    doctor_id: str,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    _ = user_id
    return await _node_request(
        "PATCH",
        "/doctor",
        json_body={"doctorId": doctor_id.strip()},
        bearer_token=bearer_token,
    )


async def update_profile(
    user_id: str,
    body: HlhpProfileUpdateRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Profile city comes from Node GET goals.profile — do not hub-write goal keys."""
    _ = body
    data = await get_goals(bearer_token=bearer_token)
    profile = data.get("profile") if isinstance(data, dict) else None
    return profile if isinstance(profile, dict) else {"userId": user_id}
