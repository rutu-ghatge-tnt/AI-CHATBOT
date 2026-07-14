"""HLHP shared chat — publish/read via hub."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from app.hlhp.core.bus_client import get_bus_client
from app.hlhp.models.hlhp_bus import HlhpChatMessageRequest, HlhpTypingRequest


def _now_ms() -> int:
    return int(time.time() * 1000)


def _format_time(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(ts_ms / 1000)
        .strftime("%I:%M %p")
        .lstrip("0")
        .lower()
    )


async def get_chat_state(
    seeker_id: str,
    doctor_id: str | None = None,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    if not client.configured:
        return {"messages": [], "readState": {}, "subscriptionFee": None}

    state = await client.get_state(
        seeker_id=seeker_id,
        doctor_id=doctor_id,
        bearer_token=bearer_token,
    )
    messages = state.get("hlhp_shared_chat_v1") or []
    reads = state.get("hlhp_chat_reads_v1") or {}
    sub = state.get("hlhp_subscription_v1") or {}
    if not isinstance(messages, list):
        messages = []
    if not isinstance(reads, dict):
        reads = {}
    fee = sub.get("fee") if isinstance(sub, dict) else None
    return {"messages": messages, "readState": reads, "subscriptionFee": fee}


async def post_seeker_message(
    seeker_id: str,
    body: HlhpChatMessageRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    ts = _now_ms()
    msg = {
        "who": "seeker",
        "txt": (body.txt or "").strip(),
        "photo": bool(body.photo),
        "time": _format_time(ts),
        "ts": ts,
    }
    if client.configured:
        await client.publish(
            "hlhp_shared_chat_v1",
            msg,
            seeker_id=seeker_id,
            doctor_id=body.doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=seeker_id,
            on_behalf_role="seeker",
        )
    return {"ok": True, "message": msg}


async def mark_seeker_read(
    seeker_id: str,
    *,
    doctor_id: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    payload = {"seeker": _now_ms()}
    if client.configured:
        await client.publish(
            "hlhp_chat_reads_v1",
            payload,
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=seeker_id,
            on_behalf_role="seeker",
        )
    return {"ok": True}


async def post_seeker_typing(
    seeker_id: str,
    body: HlhpTypingRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    payload = {
        "who": "seeker",
        "thread": seeker_id,
        "on": bool(body.on),
        "ts": _now_ms(),
    }
    if client.configured:
        await client.publish(
            "hlhp_typing_v1",
            payload,
            seeker_id=seeker_id,
            doctor_id=body.doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=seeker_id,
            on_behalf_role="seeker",
        )
    return {"ok": True, "transient": True}
