"""Best-effort publish of daily logs onto the Node HLHP bus.

Mongo remains the source of truth for Fun coach history. The bus append
(`hlhp_daily_log_v1`) is a cross-app fan-out for dermat/admin — never block
the seeker log write if the hub is down.
"""

from __future__ import annotations

import logging
from typing import Any

from app.hlhp.core.bus_client import HlhpHubError, get_bus_client
from app.hlhp.core.chat_payload import now_ms
from app.hlhp.core.hub_state import get_bus_value

logger = logging.getLogger(__name__)


def _resolve_doctor_id(
    state: dict[str, Any],
    seeker_id: str,
    doctor_id: str | None,
) -> str | None:
    if doctor_id and doctor_id.strip():
        return doctor_id.strip()
    goal = get_bus_value(state, "hlhp_goal_setup_v1", seeker_id=seeker_id)
    if isinstance(goal, dict):
        assigned = str(goal.get("assignedDoctorId") or "").strip()
        if assigned:
            return assigned
    return None


async def publish_daily_log_best_effort(
    seeker_id: str,
    *,
    symptoms: list[str],
    areas: list[str],
    sfi: int,
    notes: str | None = None,
    outdoor_exposure: str | None = None,
    selfie: bool = False,
    selfie_url: str | None = None,
    streak: int | None = None,
    date_key: str | None = None,
    doctor_id: str | None = None,
    bearer_token: str | None = None,
    ts_ms: int | None = None,
) -> bool:
    """Append ``hlhp_daily_log_v1``. Returns True when a publish was attempted and applied."""
    client = get_bus_client()
    if not client.configured:
        return False

    resolved_doctor = doctor_id
    try:
        state = await client.get_state(
            seeker_id=seeker_id,
            doctor_id=doctor_id,
            bearer_token=bearer_token,
            as_role="seeker",
        )
        resolved_doctor = _resolve_doctor_id(state, seeker_id, doctor_id)
    except HlhpHubError as exc:
        logger.warning("HLHP daily_log doctor resolve skipped: %s", exc.message)
        state = {}

    if not resolved_doctor:
        # Lane keys require a doctorId for seeker writes on Node Phase 1.
        logger.info(
            "HLHP daily_log bus publish skipped — no assigned doctor for seeker %s",
            seeker_id,
        )
        return False

    payload: dict[str, Any] = {
        "symptoms": list(symptoms),
        "areas": list(areas),
        "sfi": int(sfi),
        "selfie": bool(selfie) or bool(selfie_url),
        "ts": ts_ms if ts_ms is not None else now_ms(),
    }
    if notes:
        payload["notes"] = notes
    if outdoor_exposure:
        payload["outdoorExposure"] = outdoor_exposure
    if selfie_url:
        payload["selfieImg"] = selfie_url
        payload["img"] = selfie_url
    if streak is not None:
        payload["streak"] = int(streak)
    if date_key:
        payload["date"] = date_key

    try:
        await client.publish(
            "hlhp_daily_log_v1",
            payload,
            seeker_id=seeker_id,
            doctor_id=resolved_doctor,
            bearer_token=bearer_token,
            on_behalf_user_id=seeker_id,
            on_behalf_role="seeker",
            as_role="seeker",
            src="ai-tools-log",
        )
        return True
    except HlhpHubError as exc:
        logger.warning(
            "HLHP daily_log bus publish failed for %s: %s",
            seeker_id,
            exc.message,
        )
        return False
