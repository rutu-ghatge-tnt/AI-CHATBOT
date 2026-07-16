"""HLHP shared chat — publish/read via Node hub (text, image URL, docs)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, UploadFile

from app.hlhp.core.bus_client import (
    get_bus_client,
    normalize_media_upload_response,
)
from app.hlhp.core.chat_payload import ChatPayloadError, build_chat_message, now_ms
from app.hlhp.core.hlhp_settings import get_hlhp_settings
from app.hlhp.core.hub_state import get_bus_value, lane_bucket
from app.hlhp.models.hlhp_bus import HlhpChatMessageRequest, HlhpTypingRequest

_ALLOWED_MEDIA_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "application/pdf",
    }
)


def _chat_page_meta(
    state: dict[str, Any],
    *,
    seeker_id: str,
    doctor_id: str | None,
) -> dict[str, Any] | None:
    top = state.get("chatPagination")
    if isinstance(top, dict):
        return top
    lane = lane_bucket(state, seeker_id=seeker_id, doctor_id=doctor_id)
    page = lane.get("__chatPage")
    return page if isinstance(page, dict) else None


async def get_chat_state(
    seeker_id: str,
    doctor_id: str | None = None,
    *,
    bearer_token: str | None = None,
    chat_limit: int | None = None,
    chat_before_ts: int | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    if not client.configured:
        return {
            "messages": [],
            "readState": {},
            "subscriptionFee": None,
            "payment": None,
            "accepted": None,
            "chatPagination": None,
        }

    state = await client.get_state(
        seeker_id=seeker_id,
        doctor_id=doctor_id,
        bearer_token=bearer_token,
        as_role="seeker",
        chat_limit=chat_limit,
        chat_before_ts=chat_before_ts,
    )
    messages = get_bus_value(
        state, "hlhp_shared_chat_v1", seeker_id=seeker_id, doctor_id=doctor_id
    )
    reads = get_bus_value(
        state, "hlhp_chat_reads_v1", seeker_id=seeker_id, doctor_id=doctor_id
    )
    sub = get_bus_value(
        state, "hlhp_subscription_v1", seeker_id=seeker_id, doctor_id=doctor_id
    )
    payment = get_bus_value(
        state, "hlhp_payment_v1", seeker_id=seeker_id, doctor_id=doctor_id
    )
    accept = get_bus_value(
        state, "hlhp_panel_accept_v1", seeker_id=seeker_id, doctor_id=doctor_id
    )

    if not isinstance(messages, list):
        messages = []
    if not isinstance(reads, dict):
        reads = {}
    fee = sub.get("fee") if isinstance(sub, dict) else None

    return {
        "messages": messages,
        "readState": reads,
        "subscriptionFee": fee,
        "payment": payment if isinstance(payment, dict) else None,
        "accepted": accept if isinstance(accept, dict) else None,
        "doctorId": doctor_id,
        "chatPagination": _chat_page_meta(
            state, seeker_id=seeker_id, doctor_id=doctor_id
        ),
    }


async def post_seeker_message(
    seeker_id: str,
    body: HlhpChatMessageRequest,
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    if not (body.doctor_id or "").strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "hlhp_chat_doctor_required",
                "message": "doctorId is required to publish a lane chat message",
            },
        )

    try:
        msg = build_chat_message(
            who="seeker",
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
            doctor_id=body.doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=seeker_id,
            on_behalf_role="seeker",
            as_role="seeker",
        )
    return {"ok": True, "message": msg}


async def mark_seeker_read(
    seeker_id: str,
    *,
    doctor_id: str | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    client = get_bus_client()
    # Field-merge shape used by the reference hub + FE: { seeker: tsMs, doctor: tsMs }
    payload = {"seeker": now_ms()}
    if client.configured:
        await client.publish(
            "hlhp_chat_reads_v1",
            payload,
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            on_behalf_user_id=seeker_id,
            on_behalf_role="seeker",
            as_role="seeker",
        )
    return {"ok": True, "readState": payload}


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
        "ts": now_ms(),
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
            as_role="seeker",
        )
    return {"ok": True, "transient": True, "typing": payload}


async def upload_chat_media(
    seeker_id: str,
    uploads: list[UploadFile],
    *,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """Proxy multipart files to Node ``POST /hlhp/hub/media`` → HTTPS URLs for chat."""
    settings = get_hlhp_settings()
    client = get_bus_client()
    if not client.configured:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "hlhp_hub_unavailable",
                "message": "HLHP hub is not configured (set HLHP_HUB_URL)",
            },
        )

    if not uploads:
        raise HTTPException(
            status_code=400,
            detail={"code": "hlhp_media_empty", "message": "At least one file is required"},
        )
    if len(uploads) > settings.hub_media_max_files:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "hlhp_media_too_many",
                "message": f"Max {settings.hub_media_max_files} files per request",
            },
        )

    prepared: list[tuple[str, bytes, str]] = []
    for upload in uploads:
        raw = await upload.read()
        if not raw:
            raise HTTPException(
                status_code=400,
                detail={"code": "hlhp_media_empty_file", "message": "Empty file rejected"},
            )
        if len(raw) > settings.hub_media_max_bytes:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "hlhp_media_too_large",
                    "message": f"File exceeds {settings.hub_media_max_bytes} bytes",
                },
            )
        content_type = (upload.content_type or "").split(";")[0].strip().lower()
        if content_type and content_type not in _ALLOWED_MEDIA_TYPES:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "hlhp_media_type",
                    "message": f"Unsupported content type: {content_type}",
                },
            )
        name = (upload.filename or "upload.bin").strip() or "upload.bin"
        prepared.append((name, raw, content_type or "application/octet-stream"))

    data = await client.upload_media(
        prepared,
        bearer_token=bearer_token,
        on_behalf_user_id=seeker_id,
        on_behalf_role="seeker",
    )
    normalized = normalize_media_upload_response(data if isinstance(data, dict) else {})
    if not normalized["urls"]:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "hlhp_media_no_url",
                "message": "Hub media upload returned no HTTPS URL",
                "payload": data,
            },
        )
    return {"ok": True, **normalized}
