"""Normalize Node HLHP hub state (envelope + lane nesting).

Node Phase 1 raw shape::

    seekers[seekerUserId][doctorUserId][busKey] = …
    doctors[doctorUserId][busKey] = …

Responses may also be wrapped as ``{ statusCode, success, data }``.
This module is the single place that understands those shapes so services
stay free of nesting conditionals.
"""

from __future__ import annotations

from typing import Any

from app.hlhp.core.bus_contract import HLHP_BUS_KEYS

_BUS_KEY_SET = frozenset(HLHP_BUS_KEYS)
_DOCTOR_SNAPSHOT_KEYS = frozenset(
    {
        "hlhp_subscription_v1",
        "hlhp_doctor_onboard_v1",
        "hlhp_doctor_earnings_v1",
    }
)


def unwrap_envelope(payload: Any) -> Any:
    """Return ``data`` when SkinBB wraps a successful JSON body."""
    if not isinstance(payload, dict):
        return payload
    if "data" not in payload:
        return payload
    if "success" in payload or "statusCode" in payload:
        return payload["data"]
    return payload


def normalize_hub_state(payload: Any) -> dict[str, Any]:
    """Coerce a hub GET response into a plain state dict."""
    data = unwrap_envelope(payload)
    return data if isinstance(data, dict) else {}


def _looks_like_lane(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    return any(str(k) in _BUS_KEY_SET or str(k).startswith("hlhp_") for k in value)


def doctor_bucket(
    state: dict[str, Any],
    doctor_id: str | None,
) -> dict[str, Any]:
    """Doctor-scoped snapshots (subscription, onboard, earnings)."""
    if not doctor_id:
        return {}
    doctors = state.get("doctors")
    if isinstance(doctors, dict):
        bucket = doctors.get(doctor_id)
        if isinstance(bucket, dict):
            return bucket
    # Scoped / legacy flat responses
    return {
        key: state[key]
        for key in _DOCTOR_SNAPSHOT_KEYS
        if key in state and state[key] is not None
    }


def lane_bucket(
    state: dict[str, Any],
    *,
    seeker_id: str | None = None,
    doctor_id: str | None = None,
) -> dict[str, Any]:
    """Resolve the seeker↔doctor lane bus map from raw hub state."""
    seekers = state.get("seekers")
    if isinstance(seekers, dict) and seeker_id:
        by_doctor = seekers.get(seeker_id)
        if isinstance(by_doctor, dict):
            if doctor_id:
                nested = by_doctor.get(doctor_id)
                if isinstance(nested, dict) and _looks_like_lane(nested):
                    return nested
            if _looks_like_lane(by_doctor):
                # Legacy: seekers[seekerId][busKey]
                return by_doctor
            if doctor_id is None:
                # Single assigned doctor — common Plus path
                nested_lanes = [
                    v for v in by_doctor.values() if isinstance(v, dict) and _looks_like_lane(v)
                ]
                if len(nested_lanes) == 1:
                    return nested_lanes[0]
        return {}

    # Flat scoped snapshot (WS hello / filtered GET)
    if _looks_like_lane(state):
        return {
            str(k): v
            for k, v in state.items()
            if str(k) in _BUS_KEY_SET or str(k).startswith("hlhp_")
        }
    return {}


def get_bus_value(
    state: dict[str, Any],
    key: str,
    *,
    seeker_id: str | None = None,
    doctor_id: str | None = None,
) -> Any:
    """Read one bus key from the correct nesting level."""
    if key in _DOCTOR_SNAPSHOT_KEYS:
        bucket = doctor_bucket(state, doctor_id)
        if key in bucket:
            return bucket[key]

    lane = lane_bucket(state, seeker_id=seeker_id, doctor_id=doctor_id)
    if key in lane:
        return lane[key]

    # Last resort: top-level (older hubs / tests)
    return state.get(key)


def iter_doctor_lanes(
    state: dict[str, Any],
    doctor_id: str,
) -> list[tuple[str, dict[str, Any]]]:
    """Yield ``(seeker_id, lane)`` pairs for a doctor across nested seekers."""
    out: list[tuple[str, dict[str, Any]]] = []
    seekers = state.get("seekers")
    if not isinstance(seekers, dict):
        return out

    for seeker_id, by_doctor in seekers.items():
        if not isinstance(by_doctor, dict):
            continue
        nested = by_doctor.get(doctor_id)
        if isinstance(nested, dict) and _looks_like_lane(nested):
            out.append((str(seeker_id), nested))
            continue
        # Legacy flat lane under seeker (single-doctor demo hubs)
        if _looks_like_lane(by_doctor):
            out.append((str(seeker_id), by_doctor))
    return out
