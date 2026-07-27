"""
Unified HLHP SFI — single entry point for scoring across Fun surfaces.

All production Fun paths (scan Hello orb, /api/v2/today, city chart, timeline,
plan week, week-ahead) must call ``resolve_sfi`` so scores stay consistent.

Layer separation (decisions Q1-Q6)
----------------------------------
The SFI number is built from exactly three things:

    band points  ->  concern weights  ->  skin-type penalties
                     (clamped to environmental, hazard-capped)

Life stage (age, gender, pregnancy, PCOS, menopause) is deliberately NOT in
that stack. Scenario Library v3.6 sheets 12 and 13 specify age/gender
``risk_delta`` as a delta to *base cell risk* (0-5) with an ``addendum``
appended to L2 copy. The previous build multiplied that delta by 4 and
subtracted it from a 0-100 friendliness score, which mixed two different
quantities on two different scales.

Use ``resolve_life_stage_adjustment`` for that layer. It returns an adjusted
cell risk, an alert level, and the addenda to append -- it never touches SFI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.hlhp.evidence.scenario_store import get_scenario_store
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import AgeBracket, UserProfile
from app.hlhp.services.scenario_engine import (
    lookup_age_rule,
    lookup_gender_rule,
    resolve_library_concerns,
    resolve_life_stage,
)
from app.hlhp.services.v4_scoring_engine import V4Evaluation, evaluate_v4, mode_for_sfi

COMFORT_SFI_THRESHOLD = 75

_FACTOR_TO_DRIVER_KEY = {
    "Temperature": "temp",
    "UV": "uv",
    "Humidity": "humidity",
    "AQI": "aqi",
}

# Profile age brackets -> Scenario Library v3.6 age modifier bands.
# `Pediatric` and `Adolescent` are intentionally unreachable: SkinBB profiles
# start at 18-24. Their 12 library rules are retained for a future minor mode.
_AGE_BRACKET_TO_LIBRARY: dict[AgeBracket, str] = {
    AgeBracket.AGE_18_24: "Young Adult",
    AgeBracket.AGE_25_30: "Young Adult",
    AgeBracket.AGE_31_40: "Adult",
    AgeBracket.AGE_41_50: "Mature",
    AgeBracket.AGE_50_PLUS: "Senior",
}

# Rows ingested from the worked-example block in sheets 12/13. These are
# pipeline documentation, not rules, and must never be matched as one.
NON_RULE_STATES: frozenset[str] = frozenset({
    "step",
    "base_cell_lookup",
    "age_modifier",
    "gender_life_stage",
    "final_personalised",
})

# Library risk (0-5) -> copy register.
_RISK_TO_LEVEL = ((4, "L2"), (2, "L1"), (0, "L0"))

RISK_LEVEL_LABELS = {
    0: "Negligible", 1: "Low", 2: "Moderate",
    3: "High", 4: "Severe", 5: "Critical",
}


# --------------------------------------------------------------------------
# SFI — environment, concern, skin type only
# --------------------------------------------------------------------------

def resolve_sfi(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    surge: bool = False,
) -> V4Evaluation:
    """Authoritative SFI for all HLHP surfaces."""
    return evaluate_v4(env, profile, guest_mode=guest_mode, surge=surge)


def outdoor_ok_from_env(
    env: EnvironmentalData,
    profile: UserProfile | None = None,
    *,
    guest_mode: bool = True,
) -> tuple[int, str]:
    """V4 headline SFI + mode label — replaces legacy Outdoor-OK composite."""
    eval_ = resolve_sfi(env, profile, guest_mode=guest_mode)
    return eval_.headline_sfi, eval_.mode


def outdoor_band_for_score(score: int) -> str:
    return mode_for_sfi(int(score))


def headline_sfi(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    surge: bool = False,
) -> int:
    return resolve_sfi(env, profile, guest_mode=guest_mode, surge=surge).headline_sfi


def dominant_driver_key(
    env: EnvironmentalData,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    outdoor_score_avg: float | None = None,
) -> str | None:
    """Recap / log driver key from V4 evaluation."""
    if outdoor_score_avg is not None and outdoor_score_avg >= COMFORT_SFI_THRESHOLD:
        return "comfort"
    eval_ = resolve_sfi(env, profile, guest_mode=guest_mode)
    if eval_.headline_sfi >= COMFORT_SFI_THRESHOLD:
        return "comfort"
    return _FACTOR_TO_DRIVER_KEY.get(eval_.dominant_factor, "comfort")


# --------------------------------------------------------------------------
# Life stage — cell risk and copy, never the score
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class LifeStageAdjustment:
    """Result of applying age + gender/life-stage modifiers to a cell risk."""

    base_risk: int
    adjusted_risk: int
    gender_delta: int = 0
    age_delta: int = 0
    addenda: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    gender_rule_found: bool = False
    age_rule_found: bool = False

    @property
    def escalated(self) -> bool:
        return self.adjusted_risk > self.base_risk

    @property
    def de_escalated(self) -> bool:
        return self.adjusted_risk < self.base_risk

    @property
    def risk_label(self) -> str:
        return RISK_LEVEL_LABELS.get(self.adjusted_risk, "Moderate")

    @property
    def alert_level(self) -> str:
        for threshold, level in _RISK_TO_LEVEL:
            if self.adjusted_risk >= threshold:
                return level
        return "L0"

    @property
    def coverage_gap(self) -> bool:
        """True when neither layer had a rule for this concern."""
        return not self.gender_rule_found and not self.age_rule_found


def _is_rule(key_state: str | None) -> bool:
    return bool(key_state) and str(key_state).strip().lower() not in NON_RULE_STATES


def _delta_of(rule: dict | None) -> tuple[int, str, str, bool]:
    """(delta, addendum, action, found) — symmetric, protective values honoured."""
    if not rule or not _is_rule(rule.get("state")):
        return 0, "", "", False
    raw = rule.get("risk_delta")
    delta = int(raw) if isinstance(raw, (int, float)) else 0
    return delta, str(rule.get("addendum") or ""), str(rule.get("action") or ""), True


def resolve_life_stage_adjustment(
    base_risk: int,
    profile: UserProfile | None,
    *,
    guest_mode: bool = False,
    concern: str | None = None,
) -> LifeStageAdjustment:
    """Apply age + gender/life-stage deltas to a matched cell's 0-5 risk.

    Deltas are applied on the library's own scale, symmetrically, so the nine
    protective (negative) values are honoured. Result is clamped to 0-5.
    """
    base = max(0, min(5, int(base_risk)))
    if not profile or guest_mode:
        return LifeStageAdjustment(base_risk=base, adjusted_risk=base)

    store = get_scenario_store()
    if concern is None:
        concerns = resolve_library_concerns(profile, guest_mode)
        concern = concerns[0] if concerns else "Acne"

    g_delta, g_add, g_act, g_found = _delta_of(
        lookup_gender_rule(store, resolve_life_stage(profile), concern)
    )

    a_delta = a_found = 0
    a_add = a_act = ""
    age_band = (
        _AGE_BRACKET_TO_LIBRARY.get(profile.age_bracket)
        if profile.age_bracket
        else None
    )
    if age_band:
        a_delta, a_add, a_act, a_found = _delta_of(
            lookup_age_rule(store, age_band, concern)
        )

    adjusted = max(0, min(5, base + g_delta + a_delta))
    return LifeStageAdjustment(
        base_risk=base,
        adjusted_risk=adjusted,
        gender_delta=g_delta,
        age_delta=a_delta,
        addenda=[t for t in (g_add, a_add) if t],
        actions=[t for t in (g_act, a_act) if t],
        gender_rule_found=bool(g_found),
        age_rule_found=bool(a_found),
    )


def apply_addenda_to_l2(l2_copy: str, adjustment: LifeStageAdjustment) -> str:
    """Append life-stage addenda to L2 copy, per sheets 12/13."""
    if not adjustment.addenda:
        return l2_copy
    tail = " ".join(a.rstrip() for a in adjustment.addenda)
    body = l2_copy.rstrip()
    if body and not body.endswith((".", "!", "?")):
        body += "."
    return f"{body} {tail}".strip()
