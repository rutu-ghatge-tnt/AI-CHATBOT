"""Deliver HLHP pattern notifications from Mongo outbox to FCM (or webhook)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from app.hlhp.db import hl_db
from app.hlhp.mongo_setup import ensure_hlhp_indexes
from app.hlhp.services.pattern_push_store import get_push_tokens

logger = logging.getLogger(__name__)

_OUTBOX = "hlhp_pattern_notification_outbox"

_PUSH_KINDS = frozenset(
    {
        "push_unlock",
        "push_behind",
        "push_d2",
        "weekly_digest",
        "warn_push",
    }
)


def _notification_title(kind: str) -> str:
    return {
        "push_unlock": "Your patterns are ready",
        "push_behind": "Patterns progress",
        "push_d2": "Keep logging",
        "weekly_digest": "Your skin this week",
        "warn_push": "Weather heads-up",
    }.get(kind, "SkinBB HLHP")


def _body_for_item(item: dict[str, Any]) -> str:
    if item.get("copy"):
        return str(item["copy"])
    if item.get("kind") == "warn_push":
        driver = item.get("driver", "weather")
        symptom = item.get("symptom", "your skin")
        when = item.get("when", "soon")
        return f"{driver} may affect {symptom} {when}."
    return "Open HLHP to see your latest skin patterns."


async def _send_via_webhook(item: dict[str, Any], tokens: list[str]) -> bool:
    url = (os.getenv("HLHP_PUSH_WEBHOOK_URL") or "").strip()
    if not url:
        return False
    payload = {
        "user_id": item.get("user_id"),
        "kind": item.get("kind"),
        "title": _notification_title(str(item.get("kind") or "")),
        "body": _body_for_item(item),
        "tokens": tokens,
        "data": {
            k: str(v)
            for k, v in item.items()
            if k not in ("_id", "created_at", "delivered") and v is not None
        },
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("pattern push webhook failed user=%s: %s", item.get("user_id"), exc)
        return False


async def _send_via_fcm_legacy(item: dict[str, Any], token: str) -> bool:
    server_key = (os.getenv("HLHP_FCM_SERVER_KEY") or "").strip()
    if not server_key:
        return False
    body = _body_for_item(item)
    payload = {
        "to": token,
        "notification": {
            "title": _notification_title(str(item.get("kind") or "")),
            "body": body,
        },
        "data": {
            "kind": str(item.get("kind") or ""),
            "user_id": str(item.get("user_id") or ""),
        },
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://fcm.googleapis.com/fcm/send",
                headers={
                    "Authorization": f"key={server_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return int(data.get("failure", 0)) == 0
    except Exception as exc:
        logger.warning("pattern push FCM failed user=%s: %s", item.get("user_id"), exc)
        return False


async def deliver_pending_notifications(
    *,
    user_id: str | None = None,
    limit: int = 100,
) -> dict[str, int]:
    """Drain undelivered outbox items for one user (or globally if user_id omitted)."""
    await ensure_hlhp_indexes()
    dry_run = (os.getenv("HLHP_PUSH_DRY_RUN") or "").lower() in ("1", "true", "yes")
    webhook = bool((os.getenv("HLHP_PUSH_WEBHOOK_URL") or "").strip())
    fcm = bool((os.getenv("HLHP_FCM_SERVER_KEY") or "").strip())
    transport_ready = webhook or fcm or dry_run

    sent = 0
    skipped = 0
    failed = 0
    now = datetime.now(timezone.utc)

    filt: dict[str, Any] = {"delivered": False}
    if user_id:
        filt["user_id"] = user_id

    try:
        cursor = hl_db[_OUTBOX].find(filt).sort("created_at", 1).limit(limit)
        async for doc in cursor:
            kind = str(doc.get("kind") or "")
            user_id = str(doc.get("user_id") or "")
            if kind not in _PUSH_KINDS:
                skipped += 1
                continue

            tokens = await get_push_tokens(user_id)
            if not tokens and not dry_run:
                skipped += 1
                continue

            ok = False
            if dry_run:
                logger.info(
                    "pattern push dry-run user=%s kind=%s body=%s",
                    user_id,
                    kind,
                    _body_for_item(doc),
                )
                ok = True
            elif webhook:
                ok = await _send_via_webhook(doc, tokens)
            elif fcm and tokens:
                ok = await _send_via_fcm_legacy(doc, tokens[0])

            if ok:
                await hl_db[_OUTBOX].update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "delivered": True,
                            "delivered_at": now,
                            "delivery_channel": (
                                "dry_run"
                                if dry_run
                                else "webhook"
                                if webhook
                                else "fcm_legacy"
                            ),
                        }
                    },
                )
                sent += 1
            else:
                failed += 1
    except Exception as exc:
        logger.warning("pattern push consumer failed: %s", exc)

    if not transport_ready and sent == 0 and skipped == 0:
        logger.debug(
            "pattern push consumer idle — set HLHP_PUSH_WEBHOOK_URL, HLHP_FCM_SERVER_KEY, or HLHP_PUSH_DRY_RUN"
        )

    return {"sent": sent, "skipped": skipped, "failed": failed}
