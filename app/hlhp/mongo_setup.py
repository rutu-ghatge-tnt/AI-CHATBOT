"""HLHP Mongo indexes and TTL retention (idempotent, safe on startup)."""

from __future__ import annotations

import logging

from app.hlhp.db import hl_db

logger = logging.getLogger(__name__)

_indexes_ensured = False

# Seconds after the indexed date field before Mongo TTL removes the document.
_LOG_EVENTS_TTL_SEC = 90 * 24 * 3600
_FEELING_LOG_TTL_SEC = 90 * 24 * 3600
_SCAN_LOG_TTL_SEC = 60 * 24 * 3600
_ACTION_LOG_TTL_SEC = 90 * 24 * 3600


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


async def ensure_hlhp_indexes() -> None:
    """Create HLHP collection indexes and TTL policies."""
    global _indexes_ensured
    if _indexes_ensured:
        return

    try:
        log_events = hl_db["hlhp_user_log_events"]
        await _safe_create_index(log_events, [("user_id", 1), ("date", -1)])
        await _safe_create_index(log_events, [("user_id", 1), ("ts", -1)])
        await _safe_create_index(log_events, "ts", expireAfterSeconds=_LOG_EVENTS_TTL_SEC)

        daily_log = hl_db["hlhp_daily_log"]
        await _safe_create_index(daily_log, [("user_id", 1), ("date", -1)], unique=True)
        await _safe_create_index(daily_log, "updated_at")

        feelings = hl_db["hlhp_symptom_feeling_log"]
        await _safe_create_index(feelings, [("user_id", 1), ("recorded_at", -1)])
        await _safe_create_index(
            feelings, [("user_id", 1), ("symptom_keyword", 1), ("recorded_at", -1)]
        )
        await _safe_create_index(
            feelings, "recorded_at", expireAfterSeconds=_FEELING_LOG_TTL_SEC
        )

        scan_log = hl_db["hlhp_scan_log"]
        await _safe_create_index(scan_log, [("user_id", 1), ("scanned_at", -1)])
        # Existing prod index may lack TTL — do not fail the whole setup on conflict.
        await _safe_create_index(scan_log, "scanned_at", expireAfterSeconds=_SCAN_LOG_TTL_SEC)

        consent = hl_db["hlhp_user_consent"]
        await _safe_create_index(consent, "user_id", unique=True)

        actions = hl_db["hlhp_action_log"]
        await _safe_create_index(actions, [("user_id", 1), ("tapped_at", -1)])
        await _safe_create_index(actions, "tapped_at", expireAfterSeconds=_ACTION_LOG_TTL_SEC)

        streaks = hl_db["hlhp_streak_counters"]
        await _safe_create_index(streaks, [("user_id", 1), ("streak_key", 1)], unique=True)

        symptoms = hl_db["hlhp_symptom_tap_log"]
        await _safe_create_index(symptoms, [("user_id", 1), ("tapped_at", -1)])

        surfaced = hl_db["hlhp_surfaced_rule_log"]
        await _safe_create_index(surfaced, [("user_id", 1), ("surfaced_at", -1)])

        nuggets = hl_db["hlhp_nugget_log"]
        await _safe_create_index(nuggets, [("user_id", 1), ("shown_at", -1)])

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
        logger.info("HLHP Mongo indexes ensured")
    except Exception as exc:
        # Still mark attempted so we do not re-run full index DDL on every request.
        _indexes_ensured = True
        logger.warning("HLHP Mongo index setup incomplete: %s", exc)
