"""Map user profile concerns to workbook concern slugs (single source of truth)."""

from __future__ import annotations

from typing import Any

from app.hlhp.models.profile import Gender, UserProfile

_CONCERN_ALIASES: dict[str, str] = {
    "teen_acne": "acne",
    "pigmentation_pih": "pigmentation_pih",
    "pigmentation": "pigmentation_pih",
    "open_pores": "open_pores",
    "pores": "open_pores",
    "texture": "open_pores",
    "dryness": "dryness",
    "dehydration": "dryness",
    "skin_tan": "skin_tan",
    "tan": "skin_tan",
    "oily_skin": "oily_skin",
    "oily": "oily_skin",
    "redness": "sensitivity",
    "melasma": "melasma",
    "sensitivity": "sensitivity",
    "dark_circles": "dark_circles",
    "aging": "aging",
    "acne": "acne",
    "hair_loss": "hair_loss",
}

_PROFILE_TO_SLUG: dict[str, str] = {
    "acne": "acne",
    "pigmentation": "pigmentation_pih",
    "melasma": "melasma",
    "tan": "skin_tan",
    "pores": "open_pores",
    "texture": "open_pores",
    "dullness": "dullness",
    "sensitivity": "sensitivity",
    "dehydration": "dryness",
    "redness": "sensitivity",
    "dark_circles": "dark_circles",
    "aging": "aging",
}

# Workbook nugget audiences that overlap dullness content (UV, pigment, glow).
_NUGGET_AUDIENCE_EXPANSION: dict[str, frozenset[str]] = {
    "dullness": frozenset({"dullness", "pigmentation_pih", "melasma", "skin_tan", "aging"}),
}

_LIFECYCLE_MARKERS = (
    "pregnancy",
    "pregnant",
    "postpartum",
    "trimester",
    "lactat",
    "menopaus",
    "postnatal",
    "breastfeed",
)


def normalize_concern_slug(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if key in _CONCERN_ALIASES:
        return _CONCERN_ALIASES[key]
    if key in _PROFILE_TO_SLUG:
        return _PROFILE_TO_SLUG[key]
    return key


def concern_slug_from_profile(profile: UserProfile | None) -> str | None:
    if not profile or not profile.skin_concerns:
        return None
    return normalize_concern_slug(profile.primary_concern.value)


def profile_concern_slugs(
    profile: UserProfile | None,
    *,
    fallback_concern_id: str | None = None,
) -> frozenset[str]:
    """User's captured concerns — no workbook expansion (unlike nugget_audience_slugs)."""
    slugs: set[str] = set()
    if profile and profile.skin_concerns:
        for item in profile.skin_concerns:
            slug = normalize_concern_slug(item.value)
            if slug:
                slugs.add(slug)
    if not slugs and fallback_concern_id:
        slug = normalize_concern_slug(fallback_concern_id)
        if slug:
            slugs.add(slug)
    return frozenset(slugs)


def nugget_audience_slugs(concern_id: str | None) -> frozenset[str] | None:
    """Slugs used to match daily nuggets — may expand beyond the display concern."""
    if not concern_id:
        return None
    slug = normalize_concern_slug(concern_id) or concern_id.lower()
    return _NUGGET_AUDIENCE_EXPANSION.get(slug, frozenset({slug}))


def resolve_concern_id(
    *,
    profile: UserProfile | None = None,
    client_concern_id: str | None = None,
) -> str | None:
    """Prefer server profile; fall back to client hint for guests."""
    from_profile = concern_slug_from_profile(profile)
    if from_profile:
        return from_profile
    return normalize_concern_slug(client_concern_id)


def nugget_matches_profile(row: dict[str, Any], profile: UserProfile | None) -> bool:
    text = str(row.get("nugget_text") or "").lower()
    if not any(marker in text for marker in _LIFECYCLE_MARKERS):
        return True
    if not profile:
        return False
    if profile.gender == Gender.MALE:
        return False
    return False
