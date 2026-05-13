from __future__ import annotations

import re
from typing import Any

from app.label_looker.engines.base_formula import apply_overrides, score_base_formula
from app.label_looker.engines.base_formula.types import BaseFormulaRecord, RuntimeContext

_TERM_ALIASES: dict[str, set[str]] = {
    "hydration": {"hydrate", "hydrating", "moisture", "moisturizing", "plumping"},
    "brightening": {"glow", "radiance", "radiant", "tone", "uneven tone"},
    "dark spots": {"dark-spot", "dark spots", "pigmentation", "hyperpigmentation", "spots"},
    "acne": {"pimples", "breakouts", "blemish"},
    "pores": {"pore", "large pores", "open pores"},
    "barrier repair": {"barrier", "repair", "skin barrier", "barrier support"},
    "soothing": {"calming", "calm", "anti-redness", "redness"},
    "oil control": {"sebum", "shine control", "mattifying"},
}


def _canonicalize_term(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    cleaned = re.sub(r"[^a-z0-9\s-]+", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    for canonical, aliases in _TERM_ALIASES.items():
        if cleaned == canonical:
            return canonical
        if cleaned in aliases:
            return canonical
    return cleaned


def _expand_text_to_terms(value: str) -> set[str]:
    text = str(value or "").strip().lower()
    if not text:
        return set()
    tokens = re.split(r"[|,/;()]+", text)
    terms: set[str] = set()
    for token in tokens:
        normalized = _canonicalize_term(token)
        if normalized:
            terms.add(normalized)
    normalized_full = _canonicalize_term(text)
    if normalized_full:
        terms.add(normalized_full)
    return terms


def skin_type_match(user_skin: str, declared_types: list[str]) -> str:
    matrix: dict[tuple[str, str], str] = {
        ("oily", "oily"): "exact",
        ("oily", "combination"): "adjacent",
        ("oily", "normal"): "adjacent",
        ("oily", "dry"): "opposite",
        ("combination", "oily"): "adjacent",
        ("combination", "combination"): "exact",
        ("combination", "normal"): "adjacent",
        ("combination", "dry"): "adjacent",
        ("normal", "oily"): "adjacent",
        ("normal", "combination"): "adjacent",
        ("normal", "normal"): "exact",
        ("normal", "dry"): "adjacent",
        ("dry", "oily"): "opposite",
        ("dry", "combination"): "adjacent",
        ("dry", "normal"): "adjacent",
        ("dry", "dry"): "exact",
    }
    matches: list[str] = []
    for declared in declared_types:
        m = matrix.get((user_skin, declared.lower().strip()))
        if m:
            matches.append(m)
    if "exact" in matches:
        return "exact"
    if "adjacent" in matches:
        return "adjacent"
    return "opposite"


def score_to_band(score: int) -> str:
    if score >= 85:
        return "great"
    if score >= 60:
        return "good"
    return "low"


def evaluate_safety(*, age: int | None, life_stages: list[str], conditions: list[str], key_ingredients: list[dict[str, Any]]) -> dict[str, Any]:
    inci = [str(k.get("inci_name") or "").strip().lower() for k in key_ingredients]
    life = {x.strip().lower() for x in life_stages if isinstance(x, str)}
    cond = {x.strip().lower() for x in conditions if isinstance(x, str)}
    triggers: list[dict[str, Any]] = []

    retinoids = {"retinol", "retinaldehyde", "retinyl palmitate", "adapalene", "tretinoin"}
    if "pregnancy" in life and any(x in retinoids for x in inci):
        triggers.append({"rule_id": "S1.PREG_RETINOID", "family": "S1", "severity": "block", "explanation": "Retinoids are not recommended during pregnancy."})
    if "pregnancy" in life and "hydroquinone" in inci:
        triggers.append({"rule_id": "S1.PREG_HYDROQUINONE", "family": "S1", "severity": "block", "explanation": "Hydroquinone is contraindicated during pregnancy."})
    if "rosacea" in cond and "alcohol denat" in inci:
        triggers.append({"rule_id": "S3.ROSACEA_ALCOHOL_DENAT", "family": "S3", "severity": "hard", "explanation": "Alcohol denat can aggravate rosacea-prone skin."})
    if isinstance(age, int) and age < 16 and "retinol" in inci:
        triggers.append({"rule_id": "S5.MINOR_RETINOL", "family": "S5", "severity": "soft", "explanation": "Retinoids are generally unnecessary under age 16 without supervision."})
    fragrance_gate = gate_fragrance_sensitivity(conditions=cond, inci=inci)
    if fragrance_gate:
        triggers.append(fragrance_gate)
    alcohol_gate = gate_alcohol_barrier(conditions=cond, inci=inci)
    if alcohol_gate:
        triggers.append(alcohol_gate)

    rank = {"clear": 0, "soft": 1, "hard": 2, "block": 3}
    severity = "clear"
    for t in triggers:
        if rank[t["severity"]] > rank[severity]:
            severity = t["severity"]
    return {"severity": severity, "triggers": triggers}


def gate_fragrance_sensitivity(*, conditions: set[str], inci: list[str]) -> dict[str, Any] | None:
    sensitive = {"sensitive skin", "sensitive_skin", "eczema", "rosacea", "barrier_compromised", "barrier compromised"}
    if not (conditions & sensitive):
        return None
    if not any(x in {"parfum", "fragrance", "perfume", "aroma"} for x in inci):
        return None
    return {
        "rule_id": "S6.SENSITIVE_FRAGRANCE",
        "family": "S6",
        "severity": "hard",
        "explanation": "Fragrance can increase irritation risk for sensitive or barrier-impaired skin.",
    }


def gate_alcohol_barrier(*, conditions: set[str], inci: list[str]) -> dict[str, Any] | None:
    barrier = {"barrier_compromised", "barrier compromised", "eczema", "rosacea"}
    if not (conditions & barrier):
        return None
    top = inci[:6]
    if not any("alcohol denat" in x or x == "ethanol" for x in top):
        return None
    return {
        "rule_id": "S7.BARRIER_ALCOHOL",
        "family": "S7",
        "severity": "hard",
        "explanation": "High-position denatured alcohol can worsen barrier impairment and stinging.",
    }


def evaluate_suitability(
    *,
    skin_type: str,
    concerns: list[str],
    benefits: list[str],
    declared_types: list[str],
    product_primary: str,
    product_benefits: list[str],
    runtime_context: RuntimeContext | None = None,
    base_formula: BaseFormulaRecord | None = None,
) -> dict[str, Any]:
    type_match = skin_type_match(skin_type.lower(), [x.lower() for x in declared_types]) if declared_types else "opposite"
    type_points = {"exact": 20, "adjacent": 10, "opposite": 0}[type_match]
    ceiling = {"exact": 100, "adjacent": 80, "opposite": 55}[type_match]

    primary = _canonicalize_term(product_primary)
    product_benefits_set: set[str] = set()
    for value in product_benefits:
        product_benefits_set.update(_expand_text_to_terms(str(value)))
    concern_weights = [(33, 20), (14, 9), (8, 5)]
    user_type_label = str(skin_type or "").strip().lower() or "not specified"
    product_type_label = ", ".join(x.strip().lower() for x in declared_types if str(x).strip()) or "not specified"
    type_note_map = {
        "exact": f"Your skin type is {user_type_label} and this product is designed for {product_type_label}, so this is a direct match.",
        "adjacent": f"Your skin type is {user_type_label} and this product is designed for {product_type_label}, so this is a close (partial) match.",
        "opposite": f"Your skin type is {user_type_label}, while this product is designed for {product_type_label}, so this is an opposite match and may not suit your current profile.",
    }
    breakdown: list[dict[str, Any]] = [{"category": "skin_type", "weight": 0.20, "answer": "yes" if type_match == "exact" else "partial" if type_match == "adjacent" else "no", "points_awarded": type_points, "note": type_note_map.get(type_match, "Type-fit data is limited for this product.")}]
    unmet_needs: list[str] = []
    concern_points = 0
    for idx, concern in enumerate(concerns[:3]):
        c = _canonicalize_term(concern)
        primary_pts, benefit_pts = concern_weights[idx]
        if c and c == primary:
            pts, ans, note = (primary_pts, "yes", f"This product directly targets your concern: {concern}.")
        elif c and c in product_benefits_set:
            pts, ans, note = (benefit_pts, "partial", f"This product partly supports your concern: {concern}.")
        else:
            pts, ans, note = (0, "no", f"This product does not clearly address your concern: {concern}.")
            if idx == 0 and c:
                unmet_needs.append(concern)
        concern_points += pts
        breakdown.append({"category": f"concern_{idx + 1}", "weight": [0.33, 0.14, 0.08][idx], "answer": ans, "points_awarded": pts, "note": note, "concern": concern})

    normalized_benefits = [_canonicalize_term(b) for b in benefits if _canonicalize_term(b)]
    benefit_match = sum(1 for b in normalized_benefits if b in product_benefits_set)
    unmatched_benefits = [b for b in normalized_benefits if b not in product_benefits_set]
    benefit_points = min(benefit_match * 2, 10)
    breakdown.append(
        {
            "category": "benefit_alignment",
            "weight": 0.10,
            "answer": "yes" if benefit_points >= 6 else "partial" if benefit_points > 0 else "no",
            "points_awarded": benefit_points,
            "note": (
                f"Your expected benefits are strongly aligned with this product ({benefit_match} out of {len(normalized_benefits)} matched)."
                if benefit_points >= 6
                else f"Some of your expected benefits are present, but not all ({benefit_match} out of {len(normalized_benefits)} matched)."
                if benefit_points > 0
                else f"Your expected benefits are not clearly supported by this formula ({benefit_match} out of {len(normalized_benefits)} matched)."
            ),
        }
    )
    base_formula_score = {"total": 0.0, "details": [], "has_finish_axis": False, "rationale_strings": []}
    if runtime_context is not None and base_formula is not None:
        base_formula_score = score_base_formula(runtime_context, base_formula)
        breakdown.append(
            {
                "category": "base_formula",
                "weight": 0.15,
                "answer": "yes" if base_formula_score["total"] >= 10 else "partial" if base_formula_score["total"] >= 6 else "no",
                "points_awarded": round(base_formula_score["total"], 2),
                "note": "; ".join(d["note"] for d in base_formula_score["details"]),
            }
        )

    raw_score = type_points + concern_points + benefit_points + float(base_formula_score["total"])
    final_score = min(raw_score, ceiling)
    override_result = None
    if runtime_context is not None and base_formula is not None:
        override_result = apply_overrides(
            ctx=runtime_context,
            base_formula=base_formula,
            suitability_score=final_score,
            base_formula_score=base_formula_score,
        )
        final_score = min(override_result["score_after"], ceiling)
    band = score_to_band(final_score)
    unmet_for_response = unmatched_benefits[:1] or unmet_needs
    return {
        "raw_score": raw_score,
        "final_score": final_score,
        "type_match": type_match,
        "type_ceiling": ceiling,
        "band": band,
        "breakdown": breakdown,
        "unmet_needs": unmet_for_response,
        "unmet_profile_concerns": unmet_needs,
        "unmatched_desired_benefits": unmatched_benefits,
        "matched_desired_benefits": [b for b in normalized_benefits if b in product_benefits_set],
        "base_formula_score": base_formula_score,
        "override_result": override_result,
    }


def evaluate_observations(
    *,
    state: str,
    safety: dict[str, Any],
    unmet_needs: list[str],
    product_primary: str,
    claims: list[str],
    base_formula: BaseFormulaRecord | None = None,
    user_flags: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    claims_set = {x.lower().strip() for x in claims if str(x).strip()}
    primary_concern = product_primary.strip().lower()

    if unmet_needs and primary_concern and primary_concern not in {x.lower() for x in unmet_needs}:
        candidates.append({"id": "M04", "family": "M", "priority": 1, "name": "Claim-to-profile mismatch", "editorial_text": "The formula appears optimized for a different primary concern than yours."})
    if unmet_needs:
        candidates.append({"id": "U03", "family": "U", "priority": 2, "name": "Gap filler direction", "editorial_text": f"Your key unmet need is {unmet_needs[0]}; consider pairing with a product that targets it directly."})
    if safety.get("severity") == "soft" and safety.get("triggers"):
        candidates.append({"id": "U04", "family": "U", "priority": 2, "name": "Soft safety context", "editorial_text": str(safety["triggers"][0].get("explanation") or "A soft safety context applies for your profile.")})
    if claims_set:
        candidates.append({"id": "F01", "family": "F", "priority": 3, "name": "Formulation orientation", "editorial_text": "The formula has clear claim alignment, but fit still depends on profile-to-concern match."})
    if base_formula:
        if str(base_formula.get("comedogenic_risk") or "") in {"high", "moderate"}:
            candidates.append(
                {
                    "id": "O10",
                    "family": "O",
                    "priority": 1,
                    "name": "Comedogenic load note",
                    "editorial_text": "This formula includes pore-clogging risk markers, so monitor congestion breakouts closely.",
                }
            )
        if str(base_formula.get("fungal_acne_safe") or "") in {"no", "caution"} and bool((user_flags or {}).get("fungal_acne_prone")):
            candidates.append(
                {
                    "id": "O11",
                    "family": "O",
                    "priority": 1,
                    "name": "Fungal-acne trigger note",
                    "editorial_text": "Potential Malassezia trigger ingredients are present for fungal-acne-prone skin.",
                }
            )
    candidates.append({"id": "C01", "family": "C", "priority": 4, "name": "Category context", "editorial_text": "This product may be solid in category terms, but personal fit is the deciding factor."})

    def eff_priority(obs: dict[str, Any]) -> int:
        p = int(obs.get("priority", 4))
        oid = str(obs.get("id") or "")
        if state == "low" and oid == "U03":
            return 0
        if state == "great" and oid == "F01":
            return 0
        return p

    ordered = sorted(candidates, key=eff_priority)
    selected: list[dict[str, Any]] = []
    has_high = any(str(x.get("family")) in ("M", "U") for x in ordered[:2])
    for obs in ordered:
        if len(selected) >= 2:
            break
        if str(obs.get("family")) == "C" and has_high:
            continue
        selected.append(obs)
    return selected

