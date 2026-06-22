"""Concern slug resolution tests."""

from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.concern_resolver import (
    concern_slug_from_profile,
    nugget_matches_profile,
    normalize_concern_slug,
    resolve_concern_id,
)


def test_normalize_concern_slug_maps_pores():
    assert normalize_concern_slug("pores") == "open_pores"
    assert normalize_concern_slug("pigmentation") == "pigmentation_pih"


def test_dullness_stays_dullness_not_acne():
    assert normalize_concern_slug("dullness") == "dullness"
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.COMBINATION,
        skin_concerns=[SkinConcern.DULLNESS, SkinConcern.DEHYDRATION, SkinConcern.PORES],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    assert concern_slug_from_profile(profile) == "dullness"
    assert resolve_concern_id(profile=profile, client_concern_id="acne") == "dullness"


def test_nugget_audience_expands_dullness():
    from app.hlhp.services.concern_resolver import nugget_audience_slugs

    slugs = nugget_audience_slugs("dullness")
    assert "dullness" in slugs
    assert "pigmentation_pih" in slugs
    assert "acne" not in slugs


def test_profile_concern_overrides_client_hint():
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.PORES],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    assert concern_slug_from_profile(profile) == "open_pores"
    assert resolve_concern_id(profile=profile, client_concern_id="melasma") == "open_pores"


def test_lifecycle_nugget_blocked_for_acne_profile():
    row = {"nugget_text": "Pregnancy-trimester acne hits many women."}
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.OILY,
        skin_concerns=[SkinConcern.ACNE],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    assert nugget_matches_profile(row, profile) is False
