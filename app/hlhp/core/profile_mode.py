"""Profile mode resolution per HLHP spec §2–§3."""

from enum import Enum

from app.hlhp.models.profile import SkinConcern, UserProfile

CAPTURED_FIELD_COUNT = 8

_PROFILE_FIELDS = (
    "age_bracket",
    "gender",
    "skin_type",
    "skin_concerns",
    "skin_goal",
    "smoking_status",
    "stress_level",
    "sleep_time",
)


class ProfileMode(str, Enum):
    GUEST = "guest"
    PARTIAL_PERSONALISED = "partial_personalised"
    PERSONALISED = "personalised"


def profile_completeness(profile: UserProfile | None) -> int:
    if profile is None:
        return 0
    score = 0
    if profile.age_bracket:
        score += 1
    if profile.gender:
        score += 1
    if profile.skin_type:
        score += 1
    if profile.skin_concerns:
        score += 1
    if profile.skin_goal:
        score += 1
    if profile.smoking_status:
        score += 1
    if profile.stress_level:
        score += 1
    if profile.sleep_time:
        score += 1
    return score


def resolve_mode(profile: UserProfile | None) -> ProfileMode:
    if profile is None:
        return ProfileMode.GUEST
    completeness = profile_completeness(profile)
    if completeness >= CAPTURED_FIELD_COUNT:
        return ProfileMode.PERSONALISED
    if completeness == 0:
        return ProfileMode.GUEST
    return ProfileMode.PARTIAL_PERSONALISED


def derive_profile_tags(profile: UserProfile) -> set[str]:
    """Derived states from spec §3.1 for future evidence-base matching."""
    tags: set[str] = {"india_default"}
    age_min = _age_bracket_min(profile.age_bracket.value if profile.age_bracket else "")
    if age_min >= 45:
        tags.add("mature")
    if age_min >= 50 and profile.gender and profile.gender.value == "female":
        tags.add("postmenopausal")
    if profile.skin_type and profile.skin_type.value == "oily" and SkinConcern.DEHYDRATION in profile.skin_concerns:
        tags.add("dehydrated_oily")
    if profile.skin_type and profile.skin_type.value == "sensitive":
        tags.add("barrier_compromised")
    if SkinConcern.SENSITIVITY in profile.skin_concerns:
        tags.add("barrier_compromised")
    if SkinConcern.ACNE in profile.skin_concerns or (
        profile.skin_type and profile.skin_type.value == "oily" and age_min < 30
    ):
        tags.add("acne_prone")
    for concern in profile.skin_concerns:
        tags.add(f"concern:{concern.value}")
    if profile.skin_type:
        tags.add(f"skin_type:{profile.skin_type.value}")
    return tags


def _age_bracket_min(bracket: str) -> int:
    if bracket.startswith("18"):
        return 18
    if bracket.startswith("25"):
        return 25
    if bracket.startswith("31"):
        return 31
    if bracket.startswith("41"):
        return 41
    if bracket.startswith("50"):
        return 50
    return 25
