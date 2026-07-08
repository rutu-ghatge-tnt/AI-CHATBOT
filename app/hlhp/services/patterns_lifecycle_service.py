"""Patterns lifecycle transitions — decay notifications and unlock side-effects."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.hlhp.db import hl_db
from app.hlhp.mongo_setup import ensure_hlhp_indexes
from app.hlhp.patterns.hlhp_patterns_engine import PatternState
from app.hlhp.patterns.hlhp_patterns_prompts import lifecycle

logger = logging.getLogger(__name__)

_OUTBOX = "hlhp_pattern_notification_outbox"


async def apply_state_transitions(
    user_id: str,
    *,
    prev_state: str,
    ps: PatternState,
    prev_decay_notified: str | None,
) -> list[dict[str, Any]]:
    """Update decay notification flags and enqueue templated copy (max 1 push per episode)."""
    notifications: list[dict[str, Any]] = []
    if prev_state == ps.state:
        return notifications

    if ps.state == "UNLOCKED_FADING" and prev_decay_notified != "UNLOCKED_FADING":
        notifications.append(
            {
                "user_id": user_id,
                "kind": "banner_fading",
                "copy": lifecycle("fading.banner"),
            }
        )
        ps.last_decay_notified_state = "UNLOCKED_FADING"

    elif ps.state == "UNLOCKED_PAUSED" and prev_decay_notified != "UNLOCKED_PAUSED":
        notifications.append(
            {
                "user_id": user_id,
                "kind": "banner_paused",
                "copy": lifecycle("paused.react"),
            }
        )
        ps.last_decay_notified_state = "UNLOCKED_PAUSED"

    elif ps.state == "UNLOCKED_ACTIVE" and prev_state in ("UNLOCKED_FADING", "UNLOCKED_PAUSED"):
        ps.last_decay_notified_state = None

    if notifications:
        await _enqueue_notifications(notifications)
    return notifications


async def notify_unlock(user_id: str) -> None:
    await _enqueue_notifications(
        [
            {
                "user_id": user_id,
                "kind": "push_unlock",
                "copy": lifecycle("unlock.push"),
            }
        ]
    )


async def enqueue_notifications(items: list[dict[str, Any]]) -> None:
    """Public entry for other modules to queue templated pattern notifications."""
    await _enqueue_notifications(items)


async def _enqueue_notifications(items: list[dict[str, Any]]) -> None:
    await ensure_hlhp_indexes()
    if not items:
        return
    now = datetime.now(timezone.utc)
    docs = [{**item, "created_at": now, "delivered": False} for item in items]
    try:
        await hl_db[_OUTBOX].insert_many(docs)
    except Exception as exc:
        logger.warning("pattern notification outbox write failed: %s", exc)


async def enqueue_pattern_alert_pushes(pushes: list[dict[str, Any]]) -> None:
    """Persist pre-emptive warn-me push descriptors from check_pattern_alerts()."""
    items = [
        {
            "user_id": p.get("user_id"),
            "kind": "warn_push",
            "pattern_id": p.get("pattern_id"),
            "driver": p.get("driver"),
            "symptom": p.get("symptom"),
            "when": p.get("when"),
            "band": p.get("band"),
        }
        for p in pushes
        if p.get("user_id")
    ]
    await _enqueue_notifications(items)
