"""HLHP goal setup and profile merge."""

from __future__ import annotations

import time
from typing import Any

from app.hlhp.core.bus_client import HlhpHubError, get_bus_client
from app.hlhp.models.hlhp_bus import HlhpGoalCreateRequest, HlhpGoalSetupPayload, HlhpProfileUpdateRequest


def _now_ms() -> int:
    return int(time.time() * 1000)


async def merge_goal_setup(
    existing: dict[str, Any] | None,
    patch: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in patch.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value.strip() if isinstance(value, str) else value
    merged["ts"] = _now_ms()
    if "profileTs" not in merged and any(k in patch for k in ("name", "city", "skin", "concern", "age", "gender")):
        merged["profileTs"] = merged["ts"]
    return merged


async def setup_goal(
    user_id: str,
    body: HlhpGoalCreateRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    existing: dict[str, Any] = {}
    if client.configured:
        try:
            state = await client.get_state(seeker_id=user_id, bearer_token=bearer_token)
            raw = state.get("hlhp_goal_setup_v1")
            if isinstance(raw, dict):
                existing = raw
        except HlhpHubError:
            existing = {}

    payload = await merge_goal_setup(
        existing,
        {
            "name": body.name,
            "goalName": body.goal_name,
            "days": body.days,
            "city": body.city,
            "skin": body.skin,
            "concern": body.concern,
            "goalFocus": body.goal_focus,
            "brief": body.brief,
            "goalType": body.goal_type,
            "age": body.age,
            "gender": body.gender,
            "assignedDoctorId": body.assigned_doctor_id,
        },
    )
    HlhpGoalSetupPayload.model_validate(payload)

    if client.configured:
        await client.publish(
            "hlhp_goal_setup_v1",
            payload,
            seeker_id=user_id,
            bearer_token=bearer_token,
            on_behalf_user_id=user_id,
            on_behalf_role="seeker",
        )
    return payload


async def update_profile(
    user_id: str,
    body: HlhpProfileUpdateRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    existing: dict[str, Any] = {}
    if client.configured:
        try:
            state = await client.get_state(seeker_id=user_id, bearer_token=bearer_token)
            raw = state.get("hlhp_goal_setup_v1")
            if isinstance(raw, dict):
                existing = raw
        except HlhpHubError:
            existing = {}

    patch = body.model_dump(exclude_none=True, exclude={"user_id"})
    if "name" in patch:
        patch["name"] = patch["name"]
    payload = await merge_goal_setup(existing, patch)

    if client.configured:
        await client.publish(
            "hlhp_goal_setup_v1",
            payload,
            seeker_id=user_id,
            bearer_token=bearer_token,
            on_behalf_user_id=user_id,
            on_behalf_role="seeker",
        )
    return payload
