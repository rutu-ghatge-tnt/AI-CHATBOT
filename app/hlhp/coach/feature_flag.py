from __future__ import annotations

import os


def coach_voice_enabled(user_id: str | None) -> bool:
    if not user_id:
        return False
    if os.getenv("HLHP_COACH_VOICE_ENABLED", "true").lower() in {"0", "false", "no"}:
        return False
    allowlist = os.getenv("HLHP_COACH_VOICE_ALLOWLIST", "").strip()
    if allowlist:
        allowed = {u.strip() for u in allowlist.split(",") if u.strip()}
        return user_id in allowed
    return True
