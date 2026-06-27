"""HLHP profile loader — Label Looker–aligned merge + mapping."""

from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    SkinConcern,
    SkinGoal,
    SkinType,
    StressLevel,
)
from app.hlhp.services.profile_loader import (
    _has_minimum_skin_profile,
    diagnose_skin_profile,
    map_merged_doc_to_user_profile,
)


def test_has_minimum_skin_profile_requires_core_fields():
    assert not _has_minimum_skin_profile({})
    assert not _has_minimum_skin_profile({"age": 25, "gender": "female"})
    assert _has_minimum_skin_profile(
        {
            "age": 25,
            "gender": "female",
            "skinType": "oily",
            "skinConcerns": ["acne"],
        }
    )


def test_map_merged_doc_acne_user_like_label_looker():
    doc = {
        "age": 28,
        "gender": "female",
        "skinType": "oily",
        "skinConcerns": ["acne", "pigmentation"],
        "skinGoals": ["acne-control"],
        "stressLevel": "moderate",
        "screenTime": "between-8-to-12-hrs",
        "skinTone": "type4",
        "firstName": "Rulu",
    }
    profile = map_merged_doc_to_user_profile("6a32a1ef9e214d0b3780c0c5", doc)
    assert profile is not None
    assert profile.skin_type == SkinType.OILY
    assert profile.skin_concerns[0] == SkinConcern.ACNE
    assert profile.gender == Gender.FEMALE
    assert profile.age_bracket == AgeBracket.AGE_25_30
    assert profile.skin_goal == SkinGoal.ACNE_CONTROL
    assert profile.stress_level == StressLevel.MODERATE
    assert profile.skin_tone_fitzpatrick == 4


def test_map_merged_doc_dark_circles_taxonomy_labels():
    doc = {
        "age": 22,
        "gender": "female",
        "skinType": "combination",
        "skinConcerns": ["dark-circles", "sleep-deprivation"],
    }
    profile = map_merged_doc_to_user_profile("user-1", doc)
    assert profile is not None
    assert SkinConcern.DARK_CIRCLES in profile.skin_concerns


def test_no_profile_when_missing_concerns():
    doc = {"age": 30, "gender": "male", "skinType": "dry"}
    assert map_merged_doc_to_user_profile("user-2", doc) is None


def test_diagnose_skin_profile_lists_missing_fields():
    diagnosis = diagnose_skin_profile({"age": 30, "gender": "female"})
    assert diagnosis["ready"] is False
    assert "skin type" in diagnosis["missing_fields"]
    assert "skin concerns" in diagnosis["missing_fields"]
    assert "incomplete" in diagnosis["message"].lower()


def test_diagnose_skin_profile_flags_unrecognized_skin_type():
    diagnosis = diagnose_skin_profile(
        {
            "age": 30,
            "gender": "female",
            "skinType": "very-oily",
            "skinConcerns": ["acne"],
        }
    )
    assert diagnosis["ready"] is False
    assert diagnosis["missing_fields"] == []
    assert diagnosis["invalid_fields"][0]["field"] == "skinType"
    assert "oily" in diagnosis["invalid_fields"][0]["accepted"]


def test_diagnose_skin_profile_flags_unmapped_concerns():
    diagnosis = diagnose_skin_profile(
        {
            "age": 30,
            "gender": "female",
            "skinType": "oily",
            "skinConcerns": ["wrinkles"],
        }
    )
    assert diagnosis["ready"] is False
    assert diagnosis["invalid_fields"][0]["field"] == "skinConcerns"
