"""Doctor panel domain helpers — panel view, CRT, tasks (scaffold)."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from app.hlhp.core.bus_client import get_bus_client
from app.hlhp.core.bus_contract import CRT_TARGET_HOURS, CRT_WINDOW_CLOSE_HOUR, CRT_WINDOW_OPEN_HOUR
from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.models.hlhp_bus import HlhpDoctorMessageRequest, HlhpDoctorOnboardComplete, HlhpDoctorSubscriptionUpdate


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
                if x.get("who") == "doctor" and x.get("ts") and _in_business_window(int(x["ts"]))
            ),
            None,
        )
        if reply:
            gaps.append((int(reply["ts"]) - int(msg["ts"])) / 3_600_000.0)
    return gaps


async def get_panel_for_doctor(
    doctor_id: str,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    if not client.configured:
        return {"doctorId": doctor_id, "seekers": [], "note": "hub not configured"}
    state = await client.get_state(doctor_id=doctor_id, bearer_token=bearer_token)
    return {"doctorId": doctor_id, "state": state, "seekers": []}


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
        )
    return {"ok": True, "fee": body.fee, "effect": "seeker Plus screens re-price live"}


async def post_doctor_message(
    doctor_id: str,
    seeker_id: str,
    body: HlhpDoctorMessageRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    ts = _now_ms()
    msg = {
        "who": "doctor",
        "txt": body.txt.strip(),
        "time": datetime.fromtimestamp(ts / 1000).strftime("%I:%M %p").lstrip("0").lower(),
        "ts": ts,
    }
    if client.configured:
        await client.publish(
            "hlhp_shared_chat_v1",
            msg,
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
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
        state = await client.get_state(doctor_id=doctor_id, bearer_token=bearer_token)
        seekers = state.get("seekers") if isinstance(state.get("seekers"), dict) else {}
        if isinstance(seekers, dict):
            for lane in seekers.values():
                if isinstance(lane, dict):
                    chat = lane.get("hlhp_shared_chat_v1") or []
                    if isinstance(chat, list):
                        gaps.extend(_crt_gaps(chat))

    avg_h = round(sum(gaps) / len(gaps), 2) if gaps else None
    on_time = round(100 * sum(1 for g in gaps if g <= CRT_TARGET_HOURS) / len(gaps)) if gaps else None
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
        )
        await client.publish(
            "hlhp_subscription_v1",
            sub,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=doctor_id,
            on_behalf_role="doctor",
        )
    return {"ok": True, "toast": "Your panel is live"}


async def default_plus_fee() -> int:
    return get_hlhp_settings().default_plus_fee_inr
