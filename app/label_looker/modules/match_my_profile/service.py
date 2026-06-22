"""Canonical service facade for Match My Profile."""

from app.label_looker.modules.match_my_profile.service_impl import (
    get_profile,
    get_scan_result,
    patch_profile,
    score_product,
    submit_feedback,
)

__all__ = ["score_product", "submit_feedback", "get_profile", "patch_profile", "get_scan_result"]

