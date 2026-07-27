"""HLHP Mongo indexes and retention policy (idempotent, safe on startup).

Training-critical user logs are stored indefinitely (no TTL).
Product query windows (History UI, patterns) stay in app code (HISTORY_UI_DAYS).
Ephemeral notification outbox keeps a short TTL.
"""

from __future__ import annotations

import logging

from app.hlhp.db import hl_db

logger = logging.getLogger(__name__)

_indexes_ensured = False

# Notification outbox only — not training data.
_OUTBOX_TTL_SEC = 90 * 24 * 3600

# Collections that must never auto-delete (AI training + long-term history).
# Existing prod TTL indexes on these are dropped on startup.
_PERMANENT_LOG_COLLECTIONS = (
    "hlhp_user_log_events",
    "hlhp_daily_log",
    "hlhp_symptom_feeling_log",
    "hlhp_scan_log",
    "hlhp_action_log",
    "hlhp_symptom_tap_log",
    "hlhp_surfaced_rule_log",
    "hlhp_nugget_log",
)


async def _safe_create_index(collection, *args, **kwargs) -> None:
    """Create an index; keep going if an equivalent/conflicting index already exists."""
    try:
        await collection.create_index(*args, **kwargs)
    except Exception as exc:
        msg = str(exc)
        code = getattr(exc, "code", None)
        if code in (85, 86) or "IndexOptionsConflict" in msg or "IndexKeySpecsConflict" in msg:
            logger.warning(
                "HLHP index skipped on %s (%s); leaving existing index as-is",
                getattr(collection, "name", collection),
                exc,
            )
            return
        raise


async def _drop_ttl_indexes(collection) -> int:
    """Remove Mongo TTL indexes so documents are no longer auto-deleted."""
    dropped = 0
    try:
        async for idx in collection.list_indexes():
            if idx.get("expireAfterSeconds") is None:
                continue
            name = idx.get("name")
            if not name or name == "_id_":
                continue
            try:
                await collection.drop_index(name)
                dropped += 1
                logger.info(
                    "HLHP dropped TTL index %s.%s (was expireAfterSeconds=%s)",
                    collection.name,
                    name,
                    idx.get("expireAfterSeconds"),
                )
            except Exception as exc:
                logger.warning(
                    "HLHP failed to drop TTL index %s.%s: %s",
                    collection.name,
                    name,
                    exc,
                )
    except Exception as exc:
        logger.warning(
            "HLHP could not list indexes on %s: %s",
            getattr(collection, "name", collection),
            exc,
        )
    return dropped


async def drop_permanent_log_ttls() -> dict[str, int]:
    """Drop TTL indexes on permanent log collections. Safe to re-run."""
    results: dict[str, int] = {}
    for name in _PERMANENT_LOG_COLLECTIONS:
        results[name] = await _drop_ttl_indexes(hl_db[name])
    return results


async def ensure_hlhp_indexes() -> None:
    """Create HLHP collection indexes; permanent logs have no TTL."""
    global _indexes_ensured
    if _indexes_ensured:
        return

    try:
        # One-time (idempotent) removal of legacy TTLs so deploy stops auto-delete.
        await drop_permanent_log_ttls()

        log_events = hl_db["hlhp_user_log_events"]
        await _safe_create_index(log_events, [("user_id", 1), ("date", -1)])
        await _safe_create_index(log_events, [("user_id", 1), ("ts", -1)])
        await _safe_create_index(log_events, "ts")

        daily_log = hl_db["hlhp_daily_log"]
        await _safe_create_index(daily_log, [("user_id", 1), ("date", -1)], unique=True)
        await _safe_create_index(daily_log, "updated_at")

        feelings = hl_db["hlhp_symptom_feeling_log"]
        await _safe_create_index(feelings, [("user_id", 1), ("recorded_at", -1)])
        await _safe_create_index(
            feelings, [("user_id", 1), ("symptom_keyword", 1), ("recorded_at", -1)]
        )
        await _safe_create_index(feelings, "recorded_at")

        scan_log = hl_db["hlhp_scan_log"]
        await _safe_create_index(scan_log, [("user_id", 1), ("scanned_at", -1)])
        await _safe_create_index(scan_log, "scanned_at")

        consent = hl_db["hlhp_user_consent"]
        await _safe_create_index(consent, "user_id", unique=True)

        actions = hl_db["hlhp_action_log"]
        await _safe_create_index(actions, [("user_id", 1), ("tapped_at", -1)])
        await _safe_create_index(actions, "tapped_at")

        streaks = hl_db["hlhp_streak_counters"]
        await _safe_create_index(streaks, [("user_id", 1), ("streak_key", 1)], unique=True)

        symptoms = hl_db["hlhp_symptom_tap_log"]
        await _safe_create_index(symptoms, [("user_id", 1), ("tapped_at", -1)])
        await _safe_create_index(symptoms, "tapped_at")

        surfaced = hl_db["hlhp_surfaced_rule_log"]
        await _safe_create_index(surfaced, [("user_id", 1), ("surfaced_at", -1)])
        await _safe_create_index(surfaced, "surfaced_at")

        nuggets = hl_db["hlhp_nugget_log"]
        await _safe_create_index(nuggets, [("user_id", 1), ("shown_at", -1)])
        await _safe_create_index(nuggets, "shown_at")

        pattern_state = hl_db["hlhp_pattern_state"]
        await _safe_create_index(pattern_state, "user_id", unique=True)

        patterns = hl_db["hlhp_patterns"]
        await _safe_create_index(patterns, [("user_id", 1), ("driver", 1), ("symptom", 1)])

        narration = hl_db["hlhp_narration_cache"]
        await _safe_create_index(narration, [("user_id", 1), ("kind", 1), ("pattern_id", 1)])

        pattern_alerts = hl_db["hlhp_pattern_alerts"]
        await _safe_create_index(pattern_alerts, [("user_id", 1), ("pattern_id", 1)], unique=True)

        outbox = hl_db["hlhp_pattern_notification_outbox"]
        await _safe_create_index(outbox, [("user_id", 1), ("created_at", -1)])
        await _safe_create_index(outbox, [("delivered", 1), ("created_at", -1)])
        await _safe_create_index(
            outbox, "created_at", expireAfterSeconds=_OUTBOX_TTL_SEC
        )

        push_tokens = hl_db["hlhp_push_tokens"]
        await _safe_create_index(push_tokens, [("user_id", 1), ("token", 1)], unique=True)
        await _safe_create_index(push_tokens, "updated_at")

        selfies = hl_db["hlhp_selfie_day"]
        await _safe_create_index(selfies, [("user_id", 1), ("date", 1)], unique=True)
        await _safe_create_index(selfies, [("user_id", 1), ("updated_at", -1)])

        # City env archive — permanent (no TTL); patterns + future training spine.
        city_daily = hl_db["hlhp_city_env_daily"]
        await _safe_create_index(city_daily, [("city_key", 1), ("date", 1)], unique=True)
        await _safe_create_index(city_daily, [("date", 1), ("city_key", 1)])
        await _safe_create_index(city_daily, [("on_board", 1), ("date", -1)])

        city_slot = hl_db["hlhp_city_env_slot"]
        await _safe_create_index(
            city_slot, [("city_key", 1), ("date", 1), ("slot_hour", 1)], unique=True
        )
        await _safe_create_index(city_slot, [("city_key", 1), ("date", 1)])
        await _safe_create_index(city_slot, [("date", 1), ("slot_hour", 1)])

        _indexes_ensured = True
        logger.info("HLHP Mongo indexes ensured (permanent logs; outbox TTL only)")
    except Exception as exc:
        # Do not mark ensured — retry on next call so TTLs are not silently skipped forever.
        logger.warning("HLHP Mongo index setup incomplete (will retry): %s", exc)
