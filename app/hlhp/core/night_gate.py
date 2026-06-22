"""Night gate — suppress sunscreen messaging when UVI is off (spec §5.3)."""

from app.hlhp.models.alert import ProtectionStep

_SUNSCREEN_MARKERS = ("spf", "sunscreen", "sun screen", "broad-spectrum", "broad spectrum")
_NIGHT_L1 = "Easy night — focus on gentle cleanse and barrier repair; save SPF for daylight."
_NIGHT_STEP = "Skip new actives tonight — cleanse gently and seal with barrier support."
_NIGHT_REASON = "UV is off; barrier recovery matters more than sun protection right now."
_GUEST_NUDGE = " Build your profile to see what this means for your skin specifically."


def is_uv_off(uv_index: float) -> bool:
    return uv_index < 1.0


def mentions_sunscreen(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _SUNSCREEN_MARKERS)


def guest_profile_nudge() -> str:
    return _GUEST_NUDGE


def apply_night_gate(
    *,
    uv_index: float,
    l1: str,
    steps: list[ProtectionStep],
    guest_mode: bool = False,
) -> tuple[str, list[ProtectionStep], str | None]:
    """Return (l1, steps, optional guest nudge suffix for whats_happening)."""
    nudge = guest_profile_nudge() if guest_mode else None

    if not is_uv_off(uv_index):
        return l1, steps, nudge

    updated_l1 = _NIGHT_L1 if mentions_sunscreen(l1) else l1
    updated_steps: list[ProtectionStep] = []
    for step in steps:
        if step.product_category == "sunscreen" or mentions_sunscreen(step.action):
            updated_steps.append(
                ProtectionStep(
                    step_number=step.step_number,
                    action=_NIGHT_STEP,
                    reason=_NIGHT_REASON,
                    product_category=step.product_category,
                )
            )
        else:
            updated_steps.append(step)
    return updated_l1, updated_steps, nudge
