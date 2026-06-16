"""Protection steps derived from evidence rows (replaces scenario L2 templates)."""

from __future__ import annotations

from app.hlhp.data.thresholds import SCENARIO_THRESHOLDS
from app.hlhp.evidence.models import EvidenceFinding
from app.hlhp.models.alert import ProtectionStep
from app.hlhp.models.environmental import EnvironmentalData

_SERUM = "Use a multi-antioxidant or niacinamide serum"
_SERUM_REASON = "Counters oxidative stress from UV and pollution."
_MOIST_HIGH = "Use a lightweight gel moisturizer"
_MOIST_LOW = "Use a barrier-support cream moisturizer"


def _looks_like_internal_token(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    # Snapshot tokens like "sleep_screen_break_periocular_care" are not user-facing copy.
    return " " not in stripped and "_" in stripped


def _category_from_text(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("sunscreen", "spf", "uv protection", "mineral")):
        return "sunscreen"
    if any(w in lower for w in ("serum", "antioxidant", "niacinamide", "vitamin c")):
        return "serum"
    if any(w in lower for w in ("moistur", "cream", "barrier", "ceramide", "gel")):
        return "moisturizer"
    if any(w in lower for w in ("cleanser", "wash")):
        return "cleanser"
    return "treatment"


def _primary_action(finding: EvidenceFinding) -> tuple[str, str, str]:
    text = finding.product_implication or finding.alert_short or finding.mechanism
    if _looks_like_internal_token(text):
        text = finding.alert_short or finding.mechanism
    if not text:
        defaults = {
            "UV": "Use broad-spectrum sunscreen before outdoor exposure",
            "Pollution": _SERUM,
            "Temperature": _MOIST_LOW,
            "Humidity": _MOIST_HIGH,
            "Nutritional Status": "Support skin with antioxidant-rich nutrition today",
            "Lifestyle": "Prioritise sleep and stress recovery for barrier health",
        }
        text = defaults.get(finding.factor, "Follow today's protective routine")
    reason = finding.mechanism or f"Supported by evidence for {finding.factor.lower()}."
    return text, reason, _category_from_text(text)


def _moisturizer_for_env(env: EnvironmentalData) -> ProtectionStep:
    if env.humidity_pct >= SCENARIO_THRESHOLDS["humidity_high"]:
        action, reason = _MOIST_HIGH, "Lightweight hydration suits humid conditions."
    else:
        action, reason = _MOIST_LOW, "Barrier support helps in dry or AC-heavy air."
    return ProtectionStep(
        step_number=3,
        action=action,
        reason=reason,
        product_category="moisturizer",
    )


def build_protection_steps(
    finding: EvidenceFinding,
    env: EnvironmentalData,
) -> list[ProtectionStep]:
    action, reason, category = _primary_action(finding)
    steps = [
        ProtectionStep(
            step_number=1,
            action=action,
            reason=reason,
            product_category=category,
        ),
    ]
    if category != "serum" and finding.factor in {"UV", "Pollution"}:
        steps.append(
            ProtectionStep(
                step_number=2,
                action=_SERUM,
                reason=_SERUM_REASON,
                product_category="serum",
            )
        )
    steps.append(_moisturizer_for_env(env))
    for i, step in enumerate(steps, start=1):
        step.step_number = i
    return steps[:3]
