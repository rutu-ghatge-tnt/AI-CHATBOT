"""HLHP spec-aligned domain logic (bands, season, profile modes, gates)."""

from app.hlhp.core.bands import EnvironmentBands, bucketize_environment
from app.hlhp.core.night_gate import apply_night_gate
from app.hlhp.core.profile_mode import ProfileMode, derive_profile_tags, profile_completeness, resolve_mode
from app.hlhp.core.season import indian_season

__all__ = [
    "EnvironmentBands",
    "bucketize_environment",
    "apply_night_gate",
    "ProfileMode",
    "derive_profile_tags",
    "profile_completeness",
    "resolve_mode",
    "indian_season",
]
