from __future__ import annotations

import re
from typing import Any


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
        triggers.append(
            {
                "rule_id": "S1.PREG_RETINOID",
                "family": "S1",
                "severity": "block",
                "explanation": "Retinoids are not recommended during pregnancy.",
            }
        )
    if "pregnancy" in life and "hydroquinone" in inci:
        triggers.append(
            {
                "rule_id": "S1.PREG_HYDROQUINONE",
                "family": "S1",
                "severity": "block",
                "explanation": "Hydroquinone is contraindicated during pregnancy.",
            }
        )
    if "rosacea" in cond and "alcohol denat" in inci:
        triggers.append(
            {
                "rule_id": "S3.ROSACEA_ALCOHOL_DENAT",
                "family": "S3",
                "severity": "hard",
                "explanation": "Alcohol denat can aggravate rosacea-prone skin.",
            }
        )
    if isinstance(age, int) and age < 16 and "retinol" in inci:
        triggers.append(
            {
                "rule_id": "S5.MINOR_RETINOL",
                "family": "S5",
                "severity": "soft",
                "explanation": "Retinoids are generally unnecessary under age 16 without supervision.",
            }
        )

    rank = {"clear": 0, "soft": 1, "hard": 2, "block": 3}
    severity = "clear"
    for t in triggers:
        if rank[t["severity"]] > rank[severity]:
            severity = t["severity"]
    return {"severity": severity, "triggers": triggers}


def evaluate_suitability(
    *,
    skin_type: str,
    concerns: list[str],
    benefits: list[str],
    declared_types: list[str],
    product_primary: str,
    product_benefits: list[str],
) -> dict[str, Any]:
    type_match = skin_type_match(skin_type.lower(), [x.lower() for x in declared_types]) if declared_types else "opposite"
    type_points = {"exact": 35, "adjacent": 17, "opposite": 0}[type_match]
    ceiling = {"exact": 100, "adjacent": 80, "opposite": 55}[type_match]

    primary = _canonicalize_term(product_primary)
    product_benefits_set: set[str] = set()
    for value in product_benefits:
        product_benefits_set.update(_expand_text_to_terms(str(value)))
    concern_weights = [(25, 15), (15, 9), (10, 6)]
    breakdown: list[dict[str, Any]] = [
        {
            "category": "skin_type",
            "weight": 0.35,
            "answer": "yes" if type_match == "exact" else "partial" if type_match == "adjacent" else "no",
            "points_awarded": type_points,
            "note": f"Type match is {type_match}",
        }
    ]
    unmet_needs: list[str] = []
    concern_points = 0
    for idx, concern in enumerate(concerns[:3]):
        c = _canonicalize_term(concern)
        primary_pts, benefit_pts = concern_weights[idx]
        if c and c == primary:
            pts, ans, note = primary_pts, "yes", "Matches primary concern"
        elif c and c in product_benefits_set:
            pts, ans, note = benefit_pts, "partial", "Covered in product benefits"
        else:
            pts, ans, note = 0, "no", "Not clearly addressed"
            if idx == 0 and c:
                unmet_needs.append(concern)
        concern_points += pts
        breakdown.append(
            {
                "category": f"concern_{idx + 1}",
                "weight": [0.25, 0.15, 0.10][idx],
                "answer": ans,
                "points_awarded": pts,
                "note": note,
                "concern": concern,
            }
        )

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
            "note": f"{benefit_match}/{len(normalized_benefits)} desired benefits matched",
        }
    )
    breakdown.append(
        {
            "category": "prac_baseline",
            "weight": 0.05,
            "answer": "yes",
            "points_awarded": 5,
            "note": "Listed product baseline",
        }
    )
    raw_score = type_points + concern_points + benefit_points + 5
    final_score = min(raw_score, ceiling)
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
    }


def evaluate_observations(
    *,
    state: str,
    safety: dict[str, Any],
    unmet_needs: list[str],
    product_primary: str,
    claims: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    claims_set = {x.lower().strip() for x in claims if str(x).strip()}
    primary_concern = product_primary.strip().lower()

    if unmet_needs and primary_concern and primary_concern not in {x.lower() for x in unmet_needs}:
        candidates.append(
            {
                "id": "M04",
                "family": "M",
                "priority": 1,
                "name": "Claim-to-profile mismatch",
                "editorial_text": "The formula appears optimized for a different primary concern than yours.",
            }
        )
    if unmet_needs:
        candidates.append(
            {
                "id": "U03",
                "family": "U",
                "priority": 2,
                "name": "Gap filler direction",
                "editorial_text": f"Your key unmet need is {unmet_needs[0]}; consider pairing with a product that targets it directly.",
            }
        )
    if safety.get("severity") == "soft" and safety.get("triggers"):
        candidates.append(
            {
                "id": "U04",
                "family": "U",
                "priority": 2,
                "name": "Soft safety context",
                "editorial_text": str(safety["triggers"][0].get("explanation") or "A soft safety context applies for your profile."),
            }
        )
    if claims_set:
        candidates.append(
            {
                "id": "F01",
                "family": "F",
                "priority": 3,
                "name": "Formulation orientation",
                "editorial_text": "The formula has clear claim alignment, but fit still depends on profile-to-concern match.",
            }
        )
    candidates.append(
        {
            "id": "C01",
            "family": "C",
            "priority": 4,
            "name": "Category context",
            "editorial_text": "This product may be solid in category terms, but personal fit is the deciding factor.",
        }
    )

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
