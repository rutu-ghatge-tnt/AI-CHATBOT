from __future__ import annotations

import re
from typing import Any

from app.label_looker.engines.base_formula import apply_overrides, score_base_formula
from app.label_looker.engines.base_formula.types import BaseFormulaRecord, RuntimeContext

_TERM_ALIASES: dict[str, set[str]] = {
    "hydration": {"hydrate", "hydrating", "moisture", "moisturizing", "plumping"},
    "brightening": {
        "glow",
        "radiance",
        "radiant",
        "tone",
        "uneven tone",
        "depigmenting",
        "depigmentation",
        "brightens",
        "brightens and evens skin tone",
        "even skin tone",
        "even tone",
        "uneven skintone",
        "uneven-skintone",
        "uneven skin tone",
        "lighter",
        "radiant skin",
        "natural glow",
    },
    "dark spots": {"dark-spot", "dark spots", "pigmentation", "hyperpigmentation", "spots", "dark-spots"},
    "dark circles": {"dark-circles", "dark circles", "under-eye", "under eye"},
    "acne": {"pimples", "breakouts", "blemish"},
    "pores": {"pore", "large pores", "open pores"},
    "barrier repair": {"barrier", "repair", "skin barrier", "barrier support"},
    "soothing": {"calming", "calm", "anti-redness", "redness"},
    "oil control": {"sebum", "shine control", "mattifying", "less oil", "less_oil"},
    "dullness": {"dull", "dull skin"},
    "spot fading": {"spot_fading", "spot fading", "fade spots"},
    "anti-aging": {"anti aging", "antiageing", "anti-ageing", "aging", "anti wrinkle", "anti-wrinkle"},
}


_LIFESTYLE_CONCERN_TERMS: set[str] = {
    "sleep deprivation",
    "sleep-deprivation",
    "sleep-deprivation-insomnia",
    "insomnia",
    "screen time",
    "screen-time",
    "stress",
    "fatigue",
    "lifestyle",
}

_PIGMENTATION_RELATED: set[str] = {"dark spots", "brightening", "pigmentation", "hyperpigmentation", "spot fading"}


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
    return cleaned.replace(" ", "-") if "-" in raw else cleaned


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


def _is_lifestyle_concern(concern: str) -> bool:
    c = _canonicalize_term(concern)
    compact = c.replace(" ", "-")
    if compact in _LIFESTYLE_CONCERN_TERMS or c in _LIFESTYLE_CONCERN_TERMS:
        return True
    return any(term in compact for term in ("sleep", "insomnia", "screen-time", "screen time"))


def skin_type_match(user_skin: str, declared_types: list[str]) -> str:
    if not declared_types:
        return "unknown"
    user = user_skin.lower().strip()
    normalized_declared = [d.lower().strip() for d in declared_types if str(d).strip()]
    # Catalog often stores "All Skin types" / "all" as a catch-all suitability row.
    if any(d in {"all", "all skin types", "all-skin-types", "all skin type"} for d in normalized_declared):
        return "exact"
    matrix: dict[tuple[str, str], str] = {
        ("oily", "oily"): "exact",
        ("oily", "combination"): "adjacent",
        ("oily", "normal"): "adjacent",
        ("oily", "dry"): "opposite",
        ("oily", "sensitive"): "adjacent",
        ("combination", "oily"): "adjacent",
        ("combination", "combination"): "exact",
        ("combination", "normal"): "adjacent",
        ("combination", "dry"): "adjacent",
        ("combination", "sensitive"): "adjacent",
        ("normal", "oily"): "adjacent",
        ("normal", "combination"): "adjacent",
        ("normal", "normal"): "exact",
        ("normal", "dry"): "adjacent",
        ("normal", "sensitive"): "adjacent",
        ("dry", "oily"): "opposite",
        ("dry", "combination"): "adjacent",
        ("dry", "normal"): "adjacent",
        ("dry", "dry"): "exact",
        ("dry", "sensitive"): "adjacent",
        ("sensitive", "sensitive"): "exact",
        ("sensitive", "dry"): "adjacent",
        ("sensitive", "normal"): "adjacent",
        ("sensitive", "combination"): "adjacent",
        ("sensitive", "oily"): "adjacent",
    }
    matches: list[str] = []
    for declared in normalized_declared:
        m = matrix.get((user, declared))
        if m:
            matches.append(m)
    if "exact" in matches:
        return "exact"
    if "adjacent" in matches:
        return "adjacent"
    return "opposite"


def hair_type_match(user_hair: str, declared_types: list[str]) -> str:
    """Hair texture fit — must not reuse the oily/dry skin matrix."""
    if not declared_types:
        return "unknown"
    user = user_hair.lower().strip().replace("_", " ").replace("-", " ")
    declared = [
        d.lower().strip().replace("_", " ").replace("-", " ")
        for d in declared_types
        if str(d).strip()
    ]
    if any(d in {"all", "all hair types", "all-hair-types"} for d in declared):
        return "exact"
    if user in declared:
        return "exact"
    adjacent: dict[str, set[str]] = {
        "straight": {"wavy"},
        "wavy": {"straight", "curly"},
        "curly": {"wavy", "coily", "kinky"},
        "coily": {"curly", "kinky"},
        "kinky": {"coily", "curly"},
    }
    near = adjacent.get(user, set())
    if near & set(declared):
        return "adjacent"
    return "opposite"


def profile_type_match(*, user_type: str, declared_types: list[str], mode: str) -> str:
    if mode == "haircare":
        return hair_type_match(user_type, declared_types)
    return skin_type_match(user_type, declared_types)


def score_to_band(score: int) -> str:
    if score >= 85:
        return "great"
    if score >= 60:
        return "good"
    if score >= 40:
        return "mixed"
    return "low"


def _skin_type_points_and_ceiling(type_match: str) -> tuple[int, int, str]:
    mapping: dict[str, tuple[int, int, str]] = {
        "exact": (30, 100, "yes"),
        "adjacent": (22, 85, "partial"),
        "unknown": (24, 100, "partial"),
        "opposite": (0, 55, "no"),
    }
    return mapping.get(type_match, (24, 100, "partial"))


def _concern_points_for_match(
    *,
    concern: str,
    primary: str,
    product_benefits_set: set[str],
    max_points: int,
) -> tuple[int, str, str]:
    c = _canonicalize_term(concern)
    if _is_lifestyle_concern(concern):
        return (
            0,
            "n/a",
            f"{concern} is a lifestyle factor — this scan focuses on formula fit for your selected benefits and skin profile.",
        )
    if c and c == primary:
        return max_points, "yes", f"This product directly targets your concern: {concern}."
    if c and c in product_benefits_set:
        pts = max(1, round(max_points * 0.55))
        return pts, "partial", f"This product partly supports your concern: {concern}."
    if c == "dark circles" and product_benefits_set & _PIGMENTATION_RELATED:
        pts = max(1, round(max_points * 0.35))
        return (
            pts,
            "partial",
            f"This product may help surface pigmentation, but under-eye dark circles ({concern}) usually need targeted eye care.",
        )
    return 0, "no", f"This product does not clearly address your concern: {concern}."


def _benefit_points(normalized_benefits: list[str], product_benefits_set: set[str]) -> tuple[int, str, str, list[str], list[str]]:
    if not normalized_benefits:
        return 0, "no", "No scan goals were provided.", [], []
    matched = [b for b in normalized_benefits if b in product_benefits_set]
    unmatched = [b for b in normalized_benefits if b not in product_benefits_set]
    total = len(normalized_benefits)
    match_count = len(matched)
    if match_count == 0:
        return (
            0,
            "no",
            f"Your selected benefits are not clearly supported by this formula (0 out of {total} matched).",
            matched,
            unmatched,
        )
    if match_count == total:
        return (
            40,
            "yes",
            f"Your selected benefits align strongly with this product ({match_count} out of {total} matched).",
            matched,
            unmatched,
        )
    points = max(8, round(40 * (match_count / total)))
    return (
        points,
        "partial",
        f"Some of your selected benefits are present ({match_count} out of {total} matched).",
        matched,
        unmatched,
    )


def _build_fit_axes(
    *,
    normalized_benefits: list[str],
    product_benefits_set: set[str],
    concerns: list[str],
    type_match: str,
    safety_severity: str = "clear",
    mode: str = "skincare",
) -> list[dict[str, Any]]:
    axes: list[dict[str, Any]] = []
    for benefit in normalized_benefits:
        matched = benefit in product_benefits_set
        axes.append(
            {
                "id": f"goal_{benefit}",
                "kind": "scan_goal",
                "label": benefit.replace("-", " ").title(),
                "status": "strong" if matched else "weak",
                "score": 92 if matched else 18,
            }
        )
    for concern in concerns[:3]:
        if _is_lifestyle_concern(concern):
            axes.append(
                {
                    "id": f"lifestyle_{_canonicalize_term(concern)}",
                    "kind": "lifestyle",
                    "label": concern.replace("-", " ").title(),
                    "status": "informational",
                    "score": None,
                    "note": "Lifestyle factors are noted but not scored against the INCI formula.",
                }
            )
            continue
        c = _canonicalize_term(concern)
        if c == "dark circles" and product_benefits_set & _PIGMENTATION_RELATED:
            status, score = "partial", 45
        elif c in product_benefits_set:
            status, score = "strong", 80
        else:
            status, score = "weak", 20
        axes.append(
            {
                "id": f"concern_{c or concern}",
                "kind": "profile_concern",
                "label": concern.replace("-", " ").title(),
                "status": status,
                "score": score,
            }
        )
    type_kind = "hair_type" if mode == "haircare" else "skin_type"
    type_label = "Hair type fit" if mode == "haircare" else "Skin type fit"
    type_note_unknown = (
        "Product hair-type targeting is not specified in catalog; formula comfort was scored separately."
        if mode == "haircare"
        else "Product skin-type targeting is not specified in catalog; formula comfort was scored separately."
    )
    if type_match == "unknown":
        axes.append(
            {
                "id": f"{type_kind}_fit",
                "kind": type_kind,
                "label": type_label,
                "status": "informational",
                "score": None,
                "note": type_note_unknown,
            }
        )
    elif type_match == "exact":
        axes.append({"id": f"{type_kind}_fit", "kind": type_kind, "label": type_label, "status": "strong", "score": 88})
    elif type_match == "adjacent":
        axes.append({"id": f"{type_kind}_fit", "kind": type_kind, "label": type_label, "status": "partial", "score": 65})
    else:
        axes.append({"id": f"{type_kind}_fit", "kind": type_kind, "label": type_label, "status": "weak", "score": 25})
    if safety_severity not in ("clear", "soft"):
        axes.append(
            {
                "id": "safety",
                "kind": "safety",
                "label": "Safety for your profile",
                "status": "caution" if safety_severity == "hard" else "blocked",
                "score": 0,
            }
        )
    return axes


def _derive_works_for_user(
    *,
    band: str,
    matched_benefits: list[str],
    unmatched_benefits: list[str],
    safety_severity: str,
) -> str:
    if safety_severity in ("block", "hard"):
        return "no"
    if unmatched_benefits:
        return "partial" if matched_benefits else "no"
    if matched_benefits and band in ("great", "good", "mixed"):
        return "yes" if band in ("great", "good") else "partial"
    if band in ("great", "good"):
        return "yes"
    if band == "mixed":
        return "partial"
    return "no"


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
    safety_severity: str = "clear",
    mode: str = "skincare",
) -> dict[str, Any]:
    type_match = profile_type_match(
        user_type=skin_type.lower(),
        declared_types=[x.lower() for x in declared_types],
        mode=mode,
    )
    type_points, ceiling, type_answer = _skin_type_points_and_ceiling(type_match)

    primary = _canonicalize_term(product_primary)
    product_benefits_set: set[str] = set()
    for value in product_benefits:
        product_benefits_set.update(_expand_text_to_terms(str(value)))

    user_type_label = str(skin_type or "").strip().lower() or "not specified"
    product_type_label = ", ".join(x.strip().lower() for x in declared_types if str(x).strip()) or "not specified in catalog"
    profile_type_word = "hair type" if mode == "haircare" else "skin type"
    type_note_map = {
        "exact": f"Your {profile_type_word} is {user_type_label} and this product is designed for {product_type_label}, so this is a direct match.",
        "adjacent": f"Your {profile_type_word} is {user_type_label} and this product is designed for {product_type_label}, so this is a close (partial) match.",
        "unknown": f"Your {profile_type_word} is {user_type_label}. This product does not list target types in our catalog, so type fit was not penalized.",
        "opposite": f"Your {profile_type_word} is {user_type_label}, while this product is designed for {product_type_label}, so this may not suit your current profile.",
    }
    type_category = "hair_type" if mode == "haircare" else "skin_type"
    breakdown: list[dict[str, Any]] = [
        {
            "category": type_category,
            "weight": 0.30,
            "answer": type_answer,
            "points_awarded": type_points,
            "note": type_note_map.get(type_match, "Type-fit data is limited for this product."),
        }
    ]

    concern_weight_schedule = [0.12, 0.05, 0.03]
    concern_point_schedule = [12, 5, 3]
    unmet_needs: list[str] = []
    concern_points = 0
    for idx, concern in enumerate(concerns[:3]):
        pts, ans, note = _concern_points_for_match(
            concern=concern,
            primary=primary,
            product_benefits_set=product_benefits_set,
            max_points=concern_point_schedule[idx],
        )
        if ans == "no" and idx == 0 and _canonicalize_term(concern) and not _is_lifestyle_concern(concern):
            unmet_needs.append(concern)
        concern_points += pts
        breakdown.append(
            {
                "category": f"concern_{idx + 1}",
                "weight": concern_weight_schedule[idx],
                "answer": ans,
                "points_awarded": pts,
                "note": note,
                "concern": concern,
            }
        )

    normalized_benefits = [_canonicalize_term(b) for b in benefits if _canonicalize_term(b)]
    benefit_points, benefit_answer, benefit_note, matched_benefits, unmatched_benefits = _benefit_points(
        normalized_benefits,
        product_benefits_set,
    )
    breakdown.append(
        {
            "category": "benefit_alignment",
            "weight": 0.40,
            "answer": benefit_answer,
            "points_awarded": benefit_points,
            "note": benefit_note,
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
    final_score = min(int(round(raw_score)), ceiling)
    override_result = None
    if runtime_context is not None and base_formula is not None:
        override_result = apply_overrides(
            ctx=runtime_context,
            base_formula=base_formula,
            suitability_score=float(final_score),
            base_formula_score=base_formula_score,
        )
        final_score = min(int(round(override_result["score_after"])), ceiling)
    band = score_to_band(final_score)
    unmet_for_response = unmatched_benefits[:1] or unmet_needs
    fit_axes = _build_fit_axes(
        normalized_benefits=normalized_benefits,
        product_benefits_set=product_benefits_set,
        concerns=concerns,
        type_match=type_match,
        safety_severity=safety_severity,
        mode=mode,
    )
    works_for_user = _derive_works_for_user(
        band=band,
        matched_benefits=matched_benefits,
        unmatched_benefits=unmatched_benefits,
        safety_severity=safety_severity,
    )
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
        "matched_desired_benefits": matched_benefits,
        "base_formula_score": base_formula_score,
        "override_result": override_result,
        "fit_axes": fit_axes,
        "works_for_user": works_for_user,
    }


def build_observation_candidates(
    *,
    safety: dict[str, Any],
    unmet_needs: list[str],
    product_primary: str,
    claims: list[str],
    base_formula: BaseFormulaRecord | None = None,
    user_flags: dict[str, Any] | None = None,
    mode: str = "skincare",
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
    if base_formula and mode != "haircare":
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
    return candidates


_OBSERVATION_FALLBACK: dict[str, dict[str, Any]] = {
    "M04": {"id": "M04", "family": "M", "priority": 1, "name": "Claim-to-profile mismatch", "editorial_text": "The formula appears optimized for a different primary concern than yours."},
    "U03": {"id": "U03", "family": "U", "priority": 2, "name": "Gap filler direction", "editorial_text": "A key profile need is not fully addressed by this formula."},
    "U04": {"id": "U04", "family": "U", "priority": 2, "name": "Soft safety context", "editorial_text": "A soft safety context applies for your profile."},
    "F01": {"id": "F01", "family": "F", "priority": 3, "name": "Formulation orientation", "editorial_text": "The formula has clear claim alignment, but fit still depends on profile-to-concern match."},
    "O10": {"id": "O10", "family": "O", "priority": 1, "name": "Comedogenic load note", "editorial_text": "This formula includes pore-clogging risk markers, so monitor congestion breakouts closely."},
    "O11": {"id": "O11", "family": "O", "priority": 1, "name": "Fungal-acne trigger note", "editorial_text": "Potential Malassezia trigger ingredients are present for fungal-acne-prone skin."},
    "C01": {"id": "C01", "family": "C", "priority": 4, "name": "Category context", "editorial_text": "This product may be solid in category terms, but personal fit is the deciding factor."},
}


def resolve_observations_by_ids(
    *,
    ids: list[str],
    safety: dict[str, Any],
    unmet_needs: list[str],
    product_primary: str = "",
    claims: list[str] | None = None,
    base_formula: BaseFormulaRecord | None = None,
    user_flags: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Rebuild full observation cards for stored ids (legacy hydration)."""
    pool = {
        str(row["id"]): row
        for row in build_observation_candidates(
            safety=safety,
            unmet_needs=unmet_needs,
            product_primary=product_primary,
            claims=claims or [],
            base_formula=base_formula,
            user_flags=user_flags,
        )
    }
    out: list[dict[str, Any]] = []
    for raw_id in ids:
        oid = str(raw_id or "").strip()
        if not oid:
            continue
        if oid in pool:
            out.append(dict(pool[oid]))
            continue
        fallback = _OBSERVATION_FALLBACK.get(oid)
        if fallback:
            out.append(dict(fallback))
    return out


def evaluate_observations(
    *,
    state: str,
    safety: dict[str, Any],
    unmet_needs: list[str],
    product_primary: str,
    claims: list[str],
    base_formula: BaseFormulaRecord | None = None,
    user_flags: dict[str, Any] | None = None,
    mode: str = "skincare",
) -> list[dict[str, Any]]:
    candidates = build_observation_candidates(
        safety=safety,
        unmet_needs=unmet_needs,
        product_primary=product_primary,
        claims=claims,
        base_formula=base_formula,
        user_flags=user_flags,
        mode=mode,
    )

    def eff_priority(obs: dict[str, Any]) -> int:
        p = int(obs.get("priority", 4))
        oid = str(obs.get("id") or "")
        if state in ("low", "mixed") and oid == "U03":
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
