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


async def ensure_hlhp_indexes() -> None:
    """Create HLHP collection indexes and TTL policies."""
    global _indexes_ensured
    if _indexes_ensured:
        return

    try:
        log_events = hl_db["hlhp_user_log_events"]
        await log_events.create_index([("user_id", 1), ("date", -1)])
        await log_events.create_index([("user_id", 1), ("ts", -1)])
        await log_events.create_index("ts", expireAfterSeconds=_LOG_EVENTS_TTL_SEC)

        daily_log = hl_db["hlhp_daily_log"]
        await daily_log.create_index([("user_id", 1), ("date", -1)], unique=True)
        await daily_log.create_index("updated_at")

        feelings = hl_db["hlhp_symptom_feeling_log"]
        await feelings.create_index([("user_id", 1), ("recorded_at", -1)])
        await feelings.create_index(
            [("user_id", 1), ("symptom_keyword", 1), ("recorded_at", -1)]
        )
        await feelings.create_index(
            "recorded_at", expireAfterSeconds=_FEELING_LOG_TTL_SEC
        )

        scan_log = hl_db["hlhp_scan_log"]
        await scan_log.create_index([("user_id", 1), ("scanned_at", -1)])
        await scan_log.create_index("scanned_at", expireAfterSeconds=_SCAN_LOG_TTL_SEC)

        consent = hl_db["hlhp_user_consent"]
        await consent.create_index("user_id", unique=True)

        actions = hl_db["hlhp_action_log"]
        await actions.create_index([("user_id", 1), ("tapped_at", -1)])
        await actions.create_index("tapped_at", expireAfterSeconds=_ACTION_LOG_TTL_SEC)

        streaks = hl_db["hlhp_streak_counters"]
        await streaks.create_index([("user_id", 1), ("streak_key", 1)], unique=True)

        symptoms = hl_db["hlhp_symptom_tap_log"]
        await symptoms.create_index([("user_id", 1), ("tapped_at", -1)])

        surfaced = hl_db["hlhp_surfaced_rule_log"]
        await surfaced.create_index([("user_id", 1), ("surfaced_at", -1)])

        nuggets = hl_db["hlhp_nugget_log"]
        await nuggets.create_index([("user_id", 1), ("shown_at", -1)])

        pattern_state = hl_db["hlhp_pattern_state"]
        await pattern_state.create_index("user_id", unique=True)

        patterns = hl_db["hlhp_patterns"]
        await patterns.create_index([("user_id", 1), ("driver", 1), ("symptom", 1)])

        narration = hl_db["hlhp_narration_cache"]
        await narration.create_index([("user_id", 1), ("kind", 1), ("pattern_id", 1)])

        pattern_alerts = hl_db["hlhp_pattern_alerts"]
        await pattern_alerts.create_index([("user_id", 1), ("pattern_id", 1)], unique=True)

        outbox = hl_db["hlhp_pattern_notification_outbox"]
        await outbox.create_index([("user_id", 1), ("created_at", -1)])
        await outbox.create_index([("delivered", 1), ("created_at", -1)])

        push_tokens = hl_db["hlhp_push_tokens"]
        await push_tokens.create_index([("user_id", 1), ("token", 1)], unique=True)
        await push_tokens.create_index("updated_at")

        _indexes_ensured = True
        logger.info("HLHP Mongo indexes ensured")
    except Exception as exc:
        logger.warning("HLHP Mongo index setup incomplete: %s", exc)
