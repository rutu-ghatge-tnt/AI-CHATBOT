from __future__ import annotations

from app.label_looker.engines.base_formula.types import BaseFormulaRecord, BaseFormulaScore, OverrideResult, RuntimeContext


def apply_overrides(
    ctx: RuntimeContext,
    base_formula: BaseFormulaRecord,
    suitability_score: float,
    base_formula_score: BaseFormulaScore,
) -> OverrideResult:
    score = suitability_score
    out = []
    blocked = False
    flags = ctx["flags"]

    seasonal = [d for d in base_formula_score["details"] if ("demoted" in d["note"] or "promoted" in d["note"])]
    if seasonal and ctx["season"] != "mar_oct_other":
        out.append(
            {
                "family": "climate_seasonal",
                "action": "demote" if "demoted" in seasonal[0]["note"] else "promote",
                "delta": 0.0,
                "reason": f"Climate ({ctx['season']}) modifier applied: {seasonal[0]['note']}",
                "affected_axis": None,
            }
        )

    if flags.get("dehydrated_oily") and base_formula.get("alcohol_level") in ("medium", "high"):
        score -= 3.0
        out.append(
            {
                "family": "dehydrated_oily",
                "action": "demote",
                "delta": -3.0,
                "reason": "Dehydrated-oily skin can worsen with drying alcohol.",
                "affected_axis": "alcohol",
            }
        )
    if flags.get("dehydrated_oily") and base_formula.get("texture") == "clay":
        score -= 2.0
        out.append(
            {
                "family": "dehydrated_oily",
                "action": "demote",
                "delta": -2.0,
                "reason": "Clay textures can worsen dehydration in oily-but-dehydrated skin.",
                "affected_axis": "texture",
            }
        )

    if flags.get("acne_prone") and base_formula.get("comedogenic_risk") == "high":
        score -= 30.0
        blocked = True
        out.append(
            {
                "family": "acne_prone",
                "action": "block",
                "delta": -30.0,
                "reason": "High comedogenic risk for acne-prone skin.",
                "affected_axis": None,
            }
        )
    if flags.get("acne_prone") and base_formula.get("texture") in ("rich_cream", "balm") and ctx.get("skin_type") in ("oily", "combination"):
        score -= 5.0
        out.append(
            {
                "family": "acne_prone",
                "action": "escalate",
                "delta": -5.0,
                "reason": "Heavy texture escalates acne-prone fit risk in oily/combination skin.",
                "affected_axis": "texture",
            }
        )
    if flags.get("acne_prone") and flags.get("fungal_acne_prone") and base_formula.get("fungal_acne_safe") == "no":
        score -= 25.0
        blocked = True
        out.append(
            {
                "family": "acne_prone",
                "action": "block",
                "delta": -25.0,
                "reason": "Contains fungal-acne trigger ingredients for fungal-acne-prone profile.",
                "affected_axis": None,
            }
        )

    if flags.get("mature_skin") and base_formula.get("texture") in ("cream", "rich_cream", "balm"):
        score += 2.0
        out.append(
            {
                "family": "mature_skin",
                "action": "promote",
                "delta": 2.0,
                "reason": "Mature skin generally tolerates richer textures better.",
                "affected_axis": "texture",
            }
        )
    if flags.get("mature_skin") and base_formula.get("continuous_phase") == "lipidic":
        score += 2.0
        out.append(
            {
                "family": "mature_skin",
                "action": "promote",
                "delta": 2.0,
                "reason": "Lipid-rich phase can support mature skin barrier.",
                "affected_axis": "carrier",
            }
        )

    if flags.get("barrier_compromised") and base_formula.get("fragrance_level") in ("low", "standard", "heavy"):
        score -= 25.0
        blocked = True
        out.append(
            {
                "family": "barrier_compromised",
                "action": "block",
                "delta": -25.0,
                "reason": "Compromised barrier with fragrance increases irritation risk.",
                "affected_axis": "fragrance",
            }
        )
    if flags.get("barrier_compromised") and base_formula.get("alcohol_level") in ("medium", "high"):
        score -= 25.0
        blocked = True
        out.append(
            {
                "family": "barrier_compromised",
                "action": "block",
                "delta": -25.0,
                "reason": "Compromised barrier with medium/high drying alcohol increases irritation risk.",
                "affected_axis": "alcohol",
            }
        )

    return OverrideResult(
        score_before=suitability_score,
        score_after=max(0.0, min(100.0, score)),
        overrides_applied=out,
        blocked=blocked,
    )

