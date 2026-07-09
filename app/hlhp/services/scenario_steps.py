"""Protection steps derived from scenario library cells."""

from __future__ import annotations

from app.hlhp.data.thresholds import SCENARIO_THRESHOLDS
from app.hlhp.models.alert import ProtectionStep
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.services.scenario_engine import ScenarioEvaluation

_SERUM = "Use a multi-antioxidant or niacinamide serum"
_SERUM_REASON = "Counters oxidative stress from UV and pollution."
_MOIST_HIGH = "Use a lightweight hydrator"
_MOIST_LOW = "Use daily hydration"


def _category_from_text(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("sunscreen", "spf", "uv protection", "mineral")):
        return "sunscreen"
    if any(w in lower for w in ("serum", "antioxidant", "niacinamide", "vitamin c")):
        return "serum"
    if any(w in lower for w in ("moistur", "cream", "barrier", "ceramide", "gel")):
        return "moisturizer"
    if any(w in lower for w in ("cleanser", "wash", "cleanse")):
        return "cleanser"
    return "treatment"


def _primary_action(scenario: ScenarioEvaluation) -> tuple[str, str, str]:
    tip = (scenario.flash_alert.tip or "").strip()
    if tip and not tip.lower().startswith("action focus:"):
        text = tip.rstrip(".")
    elif scenario.evidence_cell and scenario.evidence_cell.action:
        text = f"Focus on {scenario.evidence_cell.action.lower()} habits today"
    else:
        defaults = {
            "Temperature": "Stay cool and keep skin lightly hydrated",
            "UV": "Use broad-spectrum sunscreen before outdoor exposure",
            "AQI": _SERUM,
            "Humidity": "Keep cleansing gentle and layers lightweight",
        }
        text = defaults.get(scenario.dominant.factor, "Follow today's protective routine")
    reason = (
        (scenario.evidence_cell.evidence if scenario.evidence_cell else "")
        or f"Today's {scenario.dominant.name.lower()} reading drives this focus."
    )
    return text, reason[:220], _category_from_text(text)


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


def build_protection_steps_from_scenario(
    scenario: ScenarioEvaluation,
    env: EnvironmentalData,
) -> list[ProtectionStep]:
    action, reason, category = _primary_action(scenario)
    steps = [
        ProtectionStep(
            step_number=1,
            action=action,
            reason=reason,
            product_category=category,
        ),
    ]
    if category != "serum" and scenario.dominant.factor in {"UV", "AQI"}:
        steps.append(
            ProtectionStep(
                step_number=2,
                action=_SERUM,
                reason=_SERUM_REASON,
                product_category="serum",
            )
        )
    if category != "moisturizer":
        steps.append(_moisturizer_for_env(env))
    for i, step in enumerate(steps, start=1):
        step.step_number = i
    return steps[:3]
