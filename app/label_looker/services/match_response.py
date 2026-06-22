from __future__ import annotations

from typing import Any


def build_match_api_payload(match_result: dict[str, Any]) -> dict[str, Any]:
    """Return match score payload without duplicating the full object at every level."""
    return {
        "result": match_result,
        "scanId": match_result.get("scan_id"),
        "band": match_result.get("band"),
        "bandLabel": match_result.get("band_label"),
        "score": match_result.get("score"),
        "state": match_result.get("state"),
        "worksForUser": match_result.get("works_for_user"),
        "fitAxes": match_result.get("fit_axes", []),
        "tiles": match_result.get("tiles", {}),
        "breakdown": match_result.get("breakdown", []),
        "profileContext": match_result.get("profile_context", {}),
        "scoredFor": match_result.get("scored_for", []),
        "desiredBenefits": match_result.get("desired_benefits", []),
        "matchedDesiredBenefits": match_result.get("matched_desired_benefits", []),
        "unmatchedDesiredBenefits": match_result.get("unmatched_desired_benefits", []),
        "unmetNeeds": match_result.get("unmet_needs", []),
        "unmetProfileConcerns": match_result.get("unmet_profile_concerns", []),
        "triggeredObservations": match_result.get("triggered_observations", []),
        "safety": match_result.get("safety", {}),
        "creditsRemaining": match_result.get("credits_remaining"),
        "fullAnalysis": match_result.get("full_analysis"),
        "baseFormula": match_result.get("base_formula"),
        "ceilingApplied": match_result.get("ceiling_applied"),
        "cta": match_result.get("cta"),
        "postScanAction": match_result.get("post_scan_action"),
        "gate": match_result.get("gate"),
    }
