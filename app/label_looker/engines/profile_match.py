"""Canonical profile-match engine exports.

Engine logic lives in ``app.label_looker.engines.profile_match_impl``.
"""

from app.label_looker.engines.profile_match_impl import (
    build_observation_candidates,
    evaluate_observations,
    evaluate_safety,
    evaluate_suitability,
    resolve_observations_by_ids,
    score_to_band,
    skin_type_match,
)

__all__ = [
    "skin_type_match",
    "score_to_band",
    "evaluate_safety",
    "evaluate_suitability",
    "build_observation_candidates",
    "evaluate_observations",
    "resolve_observations_by_ids",
]

