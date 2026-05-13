"""Canonical profile-match engine exports.

Engine logic lives in ``app.label_looker.engines.profile_match_impl``.
"""

from app.label_looker.engines.profile_match_impl import (
    evaluate_observations,
    evaluate_safety,
    evaluate_suitability,
    score_to_band,
    skin_type_match,
)

__all__ = [
    "skin_type_match",
    "score_to_band",
    "evaluate_safety",
    "evaluate_suitability",
    "evaluate_observations",
]

