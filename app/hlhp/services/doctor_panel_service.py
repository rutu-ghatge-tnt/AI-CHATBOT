"""Doctor panel domain helpers — panel view, CRT, tasks (hub-backed)."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.hlhp.core.bus_client import get_bus_client
from app.hlhp.core.bus_contract import (
    CRT_TARGET_HOURS,
    CRT_WINDOW_CLOSE_HOUR,
    CRT_WINDOW_OPEN_HOUR,
)
from app.hlhp.core.chat_payload import ChatPayloadError, build_chat_message
from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.core.hub_state import doctor_bucket, iter_doctor_lanes
from app.hlhp.models.hlhp_bus import (
    HlhpDoctorMessageRequest,
    HlhpDoctorOnboardComplete,
    HlhpDoctorSubscriptionUpdate,
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _in_business_window(ts_ms: int) -> bool:
    hour = datetime.fromtimestamp(ts_ms / 1000).hour
    return CRT_WINDOW_OPEN_HOUR <= hour < CRT_WINDOW_CLOSE_HOUR


def _crt_gaps(chat: list[dict[str, Any]]) -> list[float]:
    gaps: list[float] = []
    for i, msg in enumerate(chat):
        if msg.get("who") != "seeker" or not msg.get("ts"):
            continue
        if not _in_business_window(int(msg["ts"])):
            continue
        reply = next(
            (
                x
                for x in chat[i + 1 :]
                if x.get("who") == "doctor"
                and x.get("ts")
                and _in_business_window(int(x["ts"]))
            ),
            None,
        )
        if reply:
            gaps.append((int(reply["ts"]) - int(msg["ts"])) / 3_600_000.0)
    return gaps


def _lane_summary(seeker_id: str, lane: dict[str, Any]) -> dict[str, Any]:
    goal = lane.get("hlhp_goal_setup_v1") if isinstance(lane.get("hlhp_goal_setup_v1"), dict) else {}
    pay = lane.get("hlhp_payment_v1") if isinstance(lane.get("hlhp_payment_v1"), dict) else {}
    accept = lane.get("hlhp_panel_accept_v1") if isinstance(lane.get("hlhp_panel_accept_v1"), dict) else {}
    chat = lane.get("hlhp_shared_chat_v1") if isinstance(lane.get("hlhp_shared_chat_v1"), list) else []
    reads = lane.get("hlhp_chat_reads_v1") if isinstance(lane.get("hlhp_chat_reads_v1"), dict) else {}
    doctor_read_ts = int(reads.get("doctor") or 0)
    unread = sum(
        1
        for m in chat
        if isinstance(m, dict)
        and m.get("who") == "seeker"
        and m.get("ts")
        and int(m["ts"]) > doctor_read_ts
    )
    return {
        "seekerId": seeker_id,
        "name": goal.get("name") or seeker_id,
        "goalName": goal.get("goalName") or goal.get("goal_name"),
        "city": goal.get("city"),
        "accepted": bool(accept),
        "payment": pay or None,
        "unread": unread,
        "lastMessage": chat[-1] if chat else None,
    }


async def get_panel_for_doctor(
    doctor_id: str,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    if not client.configured:
        return {"doctorId": doctor_id, "seekers": [], "note": "hub not configured"}

    state = await client.get_state(
        doctor_id=doctor_id,
        bearer_token=bearer_token,
        as_role="doctor",
    )
    lanes = iter_doctor_lanes(state, doctor_id)
    seekers = [_lane_summary(sid, lane) for sid, lane in lanes]
    doctor_state = doctor_bucket(state, doctor_id)

    return {
        "doctorId": doctor_id,
        "seekers": seekers,
        "subscription": doctor_state.get("hlhp_subscription_v1"),
        "onboard": doctor_state.get("hlhp_doctor_onboard_v1"),
        "earnings": doctor_state.get("hlhp_doctor_earnings_v1"),
    }


async def accept_seeker(
    doctor_id: str,
    seeker_id: str,
    *,
    doctor_name: str = "",
    seeker_name: str = "",
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    payload = {
        "seeker": seeker_id,
        "doctorId": doctor_id,
        "doctor": doctor_name,
        "name": seeker_name or seeker_id,
        "accepted": True,
        "ts": _now_ms(),
    }
    if client.configured:
        await client.publish(
            "hlhp_panel_accept_v1",
            payload,
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
            as_role="doctor",
        )
    return {"ok": True, "payload": payload}


async def approve_plan(
    doctor_id: str,
    seeker_id: str,
    *,
    doctor_name: str = "",
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    payload = {
        "seeker": seeker_id,
        "doctorId": doctor_id,
        "doctor": doctor_name,
        "plan": "glow",
        "ts": _now_ms(),
    }
    if client.configured:
        await client.publish(
            "hlhp_plan_approval_v1",
            payload,
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
            as_role="doctor",
        )
    return {"ok": True, "payload": payload}


async def set_subscription_fee(
    doctor_id: str,
    body: HlhpDoctorSubscriptionUpdate,
    *,
    doctor_name: str = "",
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    payload = {
        "doctorId": doctor_id,
        "doctor": doctor_name,
        "fee": body.fee,
        "ts": _now_ms(),
    }
    if client.configured:
        await client.publish(
            "hlhp_subscription_v1",
            payload,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
            as_role="doctor",
        )
    return {"ok": True, "fee": body.fee, "effect": "seeker Plus screens re-price live"}


async def post_doctor_message(
    doctor_id: str,
    seeker_id: str,
    body: HlhpDoctorMessageRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    try:
        msg = build_chat_message(
            who="doctor",
            txt=body.txt,
            photo=body.photo,
            img=body.img,
            doc=body.doc.model_dump() if body.doc else None,
        )
    except ChatPayloadError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "hlhp_chat_invalid", "message": str(exc)},
        ) from exc

    client = get_bus_client()
    if client.configured:
        await client.publish(
            "hlhp_shared_chat_v1",
            msg,
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
            as_role="doctor",
        )
    return {"ok": True, "message": msg}


async def get_crt_stats(
    doctor_id: str,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    gaps: list[float] = []
    if client.configured:
        state = await client.get_state(
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            as_role="doctor",
        )
        for _seeker_id, lane in iter_doctor_lanes(state, doctor_id):
            chat = lane.get("hlhp_shared_chat_v1") or []
            if isinstance(chat, list):
                gaps.extend(_crt_gaps([m for m in chat if isinstance(m, dict)]))

    avg_h = round(sum(gaps) / len(gaps), 2) if gaps else None
    on_time = (
        round(100 * sum(1 for g in gaps if g <= CRT_TARGET_HOURS) / len(gaps))
        if gaps
        else None
    )
    return {
        "doctorId": doctor_id,
        "targetMins": int(CRT_TARGET_HOURS * 60),
        "window": {"open": CRT_WINDOW_OPEN_HOUR, "close": CRT_WINDOW_CLOSE_HOUR},
        "avgMins": round(avg_h * 60) if avg_h is not None else None,
        "onTimePct": on_time,
        "pairs": len(gaps),
    }


async def complete_onboarding(
    doctor_id: str,
    body: HlhpDoctorOnboardComplete,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    ts = _now_ms()
    onboard = {
        "doctorId": doctor_id,
        "name": body.name,
        "quals": body.quals,
        "about": body.about,
        "city": body.city,
        "clinics": body.clinics,
        "clinicList": body.clinic_list,
        "serviceNames": body.service_names,
        "fee": body.fee,
        "ts": ts,
    }
    sub = {
        "doctorId": doctor_id,
        "doctor": body.name,
        "fee": body.fee,
        "ts": ts,
    }
    if client.configured:
        await client.publish(
            "hlhp_doctor_onboard_v1",
            onboard,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
            as_role="doctor",
        )
        await client.publish(
            "hlhp_subscription_v1",
            sub,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
            as_role="doctor",
        )
    return {"ok": True, "toast": "Your panel is live"}


async def default_plus_fee() -> int:
    return get_hlhp_settings().default_plus_fee_inr
