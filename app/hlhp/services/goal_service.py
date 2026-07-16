"""HLHP goal setup and profile merge via the Node hub."""

from __future__ import annotations

import time
from typing import Any

from app.hlhp.core.bus_client import HlhpHubError, get_bus_client
from app.hlhp.core.hub_state import get_bus_value
from app.hlhp.models.hlhp_bus import (
    HlhpGoalCreateRequest,
    HlhpGoalSetupPayload,
    HlhpProfileUpdateRequest,
)


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
    profile_keys = ("name", "city", "skin", "concern", "age", "gender")
    if "profileTs" not in merged and any(k in patch for k in profile_keys):
        merged["profileTs"] = merged["ts"]
    return merged


async def _load_existing_goal(
    user_id: str,
    *,
    doctor_id: str | None,
    bearer_token: str | None,
) -> dict[str, Any]:
    client = get_bus_client()
    if not client.configured:
        return {}
    try:
        state = await client.get_state(
            seeker_id=user_id,
            doctor_id=doctor_id or None,
            bearer_token=bearer_token,
            as_role="seeker",
        )
        raw = get_bus_value(
            state,
            "hlhp_goal_setup_v1",
            seeker_id=user_id,
            doctor_id=doctor_id or None,
        )
        return raw if isinstance(raw, dict) else {}
    except HlhpHubError:
        return {}


async def setup_goal(
    user_id: str,
    body: HlhpGoalCreateRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    doctor_id = (body.assigned_doctor_id or "").strip() or None
    existing = await _load_existing_goal(
        user_id, doctor_id=doctor_id, bearer_token=bearer_token
    )

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
            "assignedDoctorName": body.assigned_doctor_name,
        },
    )
    HlhpGoalSetupPayload.model_validate(payload)

    client = get_bus_client()
    if client.configured:
        await client.publish(
            "hlhp_goal_setup_v1",
            payload,
            seeker_id=user_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=user_id,
            on_behalf_role="seeker",
            as_role="seeker",
        )
    return payload


async def update_profile(
    user_id: str,
    body: HlhpProfileUpdateRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    existing = await _load_existing_goal(
        user_id, doctor_id=None, bearer_token=bearer_token
    )
    # Prefer lane doctor when profile merge happens after assignment
    doctor_id = str(existing.get("assignedDoctorId") or "").strip() or None

    patch = body.model_dump(exclude_none=True, exclude={"user_id"})
    payload = await merge_goal_setup(existing, patch)

    client = get_bus_client()
    if client.configured:
        await client.publish(
            "hlhp_goal_setup_v1",
            payload,
            seeker_id=user_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=user_id,
            on_behalf_role="seeker",
            as_role="seeker",
        )
    return payload
