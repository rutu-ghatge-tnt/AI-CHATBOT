"""Frozen HLHP event-bus contract — mirrors new-hlhp-ref-with-goals/backend/react/ts/hlhp-keys.ts."""

from __future__ import annotations

from typing import Final, Literal

BusKey = Literal[
    "hlhp_shared_chat_v1",
    "hlhp_daily_log_v1",
    "hlhp_goal_setup_v1",
    "hlhp_payment_v1",
    "hlhp_subscription_v1",
    "hlhp_panel_accept_v1",
    "hlhp_plan_approval_v1",
    "hlhp_doctor_onboard_v1",
    "hlhp_doctor_earnings_v1",
    "hlhp_typing_v1",
    "hlhp_chat_reads_v1",
]

BusRole = Literal["seeker", "doctor", "admin", "bridge", "service"]

HLHP_BUS_KEYS: Final[tuple[BusKey, ...]] = (
    "hlhp_shared_chat_v1",
    "hlhp_daily_log_v1",
    "hlhp_goal_setup_v1",
    "hlhp_payment_v1",
    "hlhp_subscription_v1",
    "hlhp_panel_accept_v1",
    "hlhp_plan_approval_v1",
    "hlhp_doctor_onboard_v1",
    "hlhp_doctor_earnings_v1",
    "hlhp_typing_v1",
    "hlhp_chat_reads_v1",
)

APPEND_KEYS: Final[frozenset[BusKey]] = frozenset(
    {"hlhp_shared_chat_v1", "hlhp_daily_log_v1"}
)
TRANSIENT_KEYS: Final[frozenset[BusKey]] = frozenset({"hlhp_typing_v1"})
MERGE_KEYS: Final[frozenset[BusKey]] = frozenset({"hlhp_chat_reads_v1"})
SNAPSHOT_KEYS: Final[frozenset[BusKey]] = frozenset(
    k for k in HLHP_BUS_KEYS if k not in APPEND_KEYS and k not in TRANSIENT_KEYS
)

SEEKER_WRITE_KEYS: Final[frozenset[BusKey]] = frozenset(
    {
        "hlhp_shared_chat_v1",
        "hlhp_daily_log_v1",
        "hlhp_goal_setup_v1",
        "hlhp_payment_v1",
        "hlhp_typing_v1",
        "hlhp_chat_reads_v1",
    }
)

DOCTOR_WRITE_KEYS: Final[frozenset[BusKey]] = frozenset(
    {
        "hlhp_shared_chat_v1",
        "hlhp_typing_v1",
        "hlhp_panel_accept_v1",
        "hlhp_plan_approval_v1",
        "hlhp_subscription_v1",
        "hlhp_doctor_onboard_v1",
        "hlhp_doctor_earnings_v1",
        "hlhp_chat_reads_v1",
    }
)

DEFAULT_PLUS_FEE_INR: Final[int] = 1499
DOCTOR_SHARE_PCT: Final[float] = 0.8
CRT_TARGET_HOURS: Final[float] = 2.0
CRT_WINDOW_OPEN_HOUR: Final[int] = 9
CRT_WINDOW_CLOSE_HOUR: Final[int] = 18


def role_may_write(role: str, key: str) -> bool:
    if role in ("admin", "bridge", "service"):
        return key in HLHP_BUS_KEYS
    if role == "seeker":
        return key in SEEKER_WRITE_KEYS
    if role == "doctor":
        return key in DOCTOR_WRITE_KEYS
    return False
