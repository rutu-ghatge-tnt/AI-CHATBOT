"""Load user profile from Mongo (users + user_details) for HLHP personalisation.

Uses the same merge + taxonomy resolution path as Label Looker so externalId
auth ids (e.g. 6a32a1ef9e214d0b3780c0c5) resolve to the correct user_details row.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.hlhp.db import get_hlhp_db
from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    SkinGoal,
    SkinType,
    SleepTime,
    SmokingStatus,
    StressLevel,
    UserProfile,
)
from app.hlhp.services.profile_taxonomy_mapper import (
    map_hair_concerns,
    map_hair_type,
    map_skin_concerns,
    map_skin_type,
    refresh_taxonomy_aliases_from_db,
    supported_skin_concern_examples,
)
from app.hlhp.services.user_display import extract_first_name_from_doc
from app.label_looker.services.profile_form import _list_values, _parse_age, _scalar
from app.label_looker.services.profile_taxonomy_resolver import resolve_profile_taxonomy_refs
from app.label_looker.services.user_profile_flow import (
    merge_auth_user_details,
    normalize_mongo_profile_shape,
    resolve_users_collection_id,
    user_details_lookup_filter,
    users_lookup_filter,
)

logger = logging.getLogger(__name__)

_USER_COLL = os.getenv("LABEL_LOOKER_USER_COLLECTION", "users")
_USER_DETAILS_COLL = os.getenv("LABEL_LOOKER_USER_DETAILS_COLLECTION", "user_details")

_SKIN_GOAL_MAP = {
    "prevention": SkinGoal.PREVENTION,
    "barrier_health": SkinGoal.BARRIER_HEALTH,
    "barrier-health": SkinGoal.BARRIER_HEALTH,
    "brightening": SkinGoal.BRIGHTENING,
    "glow": SkinGoal.BRIGHTENING,
    "anti_aging": SkinGoal.ANTI_AGING,
    "anti-aging": SkinGoal.ANTI_AGING,
    "acne_control": SkinGoal.ACNE_CONTROL,
    "acne-control": SkinGoal.ACNE_CONTROL,
    "hydration": SkinGoal.HYDRATION,
    "even_tone": SkinGoal.EVEN_TONE,
    "even-tone": SkinGoal.EVEN_TONE,
    "eventone": SkinGoal.EVEN_TONE,
    "general_wellness": SkinGoal.GENERAL_WELLNESS,
    "general-wellness": SkinGoal.GENERAL_WELLNESS,
}

_SMOKING_MAP = {
    "never": SmokingStatus.NEVER,
    "former": SmokingStatus.FORMER,
    "occasional": SmokingStatus.OCCASIONAL,
    "regular": SmokingStatus.REGULAR,
    "current": SmokingStatus.REGULAR,
}

_STRESS_MAP = {
    "low": StressLevel.LOW,
    "moderate": StressLevel.MODERATE,
    "high": StressLevel.HIGH,
    "very_high": StressLevel.VERY_HIGH,
    "very-high": StressLevel.VERY_HIGH,
}

_SLEEP_MAP = {
    "less_than_5h": SleepTime.LESS_THAN_5H,
    "less-than-5h": SleepTime.LESS_THAN_5H,
    "less-than-5-hrs": SleepTime.LESS_THAN_5H,
    "under_6h": SleepTime.LESS_THAN_5H,
    "5_6h": SleepTime.H5_6H,
    "5-6h": SleepTime.H5_6H,
    "between-5-to-8-hrs": SleepTime.H6_7H,
    "6_7h": SleepTime.H6_7H,
    "6-7h": SleepTime.H6_7H,
    "7_9h": SleepTime.H7_9H,
    "7-9h": SleepTime.H7_9H,
    "between-8-to-12-hrs": SleepTime.H7_9H,
    "7": SleepTime.H7_9H,
    "8": SleepTime.H7_9H,
    "more_than_9h": SleepTime.MORE_THAN_9H,
    "more-than-9h": SleepTime.MORE_THAN_9H,
    "over_8h": SleepTime.MORE_THAN_9H,
}

_SKIN_TONE_TO_FITZ: dict[str, int] = {
    "type1": 1,
    "type2": 2,
    "type3": 3,
    "type4": 4,
    "type5": 5,
    "type6": 6,
    "i": 1,
    "ii": 2,
    "iii": 3,
    "iv": 4,
    "v": 5,
    "vi": 6,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
}

# Scenario library sheet 13 — exact state labels
_LIBRARY_LIFE_STAGES = (
    "Male",
    "Female",
    "Female + Pregnancy",
    "Female + Lactation",
    "Female + Perimenopause",
    "Female + Menopause",
    "Female + Menstrual Cycle",
    "Female + PCOS",
    "Adolescent / Puberty",
)

_LIFE_STAGE_ALIASES: dict[str, str] = {
    "male": "Male",
    "female": "Female",
    "pregnancy": "Female + Pregnancy",
    "pregnant": "Female + Pregnancy",
    "female_pregnancy": "Female + Pregnancy",
    "female + pregnancy": "Female + Pregnancy",
    "lactation": "Female + Lactation",
    "nursing": "Female + Lactation",
    "breastfeeding": "Female + Lactation",
    "female_lactation": "Female + Lactation",
    "female + lactation": "Female + Lactation",
    "perimenopause": "Female + Perimenopause",
    "female_perimenopause": "Female + Perimenopause",
    "female + perimenopause": "Female + Perimenopause",
    "menopause": "Female + Menopause",
    "postmenopause": "Female + Menopause",
    "postmenopausal": "Female + Menopause",
    "female_menopause": "Female + Menopause",
    "female + menopause": "Female + Menopause",
    "menstrual_cycle": "Female + Menstrual Cycle",
    "menstrual cycle": "Female + Menstrual Cycle",
    "female_menstrual_cycle": "Female + Menstrual Cycle",
    "female + menstrual cycle": "Female + Menstrual Cycle",
    "pcos": "Female + PCOS",
    "female_pcos": "Female + PCOS",
    "female + pcos": "Female + PCOS",
    "adolescent": "Adolescent / Puberty",
    "puberty": "Adolescent / Puberty",
    "adolescent_puberty": "Adolescent / Puberty",
    "adolescent / puberty": "Adolescent / Puberty",
}

_LIFE_STAGE_PRIORITY = {
    "Female + PCOS": 90,
    "Female + Pregnancy": 85,
    "Female + Lactation": 80,
    "Female + Menopause": 75,
    "Female + Perimenopause": 70,
    "Female + Menstrual Cycle": 65,
    "Adolescent / Puberty": 60,
    "Female": 10,
    "Male": 10,
}


def _map_life_stage_alias(raw: str) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text in _LIBRARY_LIFE_STAGES:
        return text
    key = _norm_key(text).replace("-", "_")
    key2 = text.strip().lower()
    return _LIFE_STAGE_ALIASES.get(key) or _LIFE_STAGE_ALIASES.get(key2)


def _map_life_stage(doc: dict, *, gender: Gender | None) -> str | None:
    for field in ("gender_state", "genderState", "life_stage", "lifeStage"):
        scalar = _scalar(doc.get(field))
        if scalar:
            mapped = _map_life_stage_alias(str(scalar))
            if mapped:
                return mapped

    from_list: list[str] = []
    for item in _list_values(doc.get("lifeStages") or doc.get("life_stages") or []):
        mapped = _map_life_stage_alias(str(item))
        if mapped:
            from_list.append(mapped)
    if from_list:
        return max(from_list, key=lambda s: _LIFE_STAGE_PRIORITY.get(s, 0))

    if gender == Gender.MALE:
        return "Male"
    if gender in {Gender.FEMALE, Gender.NON_BINARY, Gender.OTHER, Gender.PREFER_NOT_TO_SAY}:
        return "Female"
    return None


def _norm_key(value: str) -> str:
    return re.sub(r"[\s_]+", "-", value.strip().lower())


def _map_optional_enum(raw, mapping: dict):
    if raw is None:
        return None
    if isinstance(raw, str):
        key = _norm_key(raw)
        if key in mapping:
            return mapping[key]
        return mapping.get(raw.strip().lower())
    return None


def _map_gender(raw) -> Gender | None:
    scalar = _scalar(raw)
    if not scalar or not isinstance(scalar, str):
        return None
    try:
        return Gender(scalar.strip().lower().replace("-", "_"))
    except ValueError:
        return None


def _age_to_bracket(age: int | None) -> AgeBracket | None:
    if age is None:
        return None
    if age <= 24:
        return AgeBracket.AGE_18_24
    if age <= 30:
        return AgeBracket.AGE_25_30
    if age <= 40:
        return AgeBracket.AGE_31_40
    if age <= 50:
        return AgeBracket.AGE_41_50
    return AgeBracket.AGE_50_PLUS


def _map_age_bracket(doc: dict) -> AgeBracket | None:
    age_raw = doc.get("ageBracket") or doc.get("age_bracket")
    if isinstance(age_raw, str):
        try:
            return AgeBracket(age_raw.strip())
        except ValueError:
            pass
    return _age_to_bracket(_parse_age(doc.get("age")))


def _map_skin_tone_fitzpatrick(doc: dict) -> int | None:
    raw = doc.get("skinTone") or doc.get("skin_tone") or doc.get("fitzpatrickType")
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        n = int(raw)
        return n if 1 <= n <= 6 else None
    if isinstance(raw, str):
        key = raw.strip().lower().replace(" ", "").replace("-", "")
        if key in _SKIN_TONE_TO_FITZ:
            return _SKIN_TONE_TO_FITZ[key]
        if key.isdigit():
            n = int(key)
            return n if 1 <= n <= 6 else None
    return None


def _map_sleep_time(doc: dict) -> SleepTime | None:
    for key in ("sleepTime", "sleep_time", "screenTime", "sleepDurations"):
        mapped = _map_optional_enum(doc.get(key), _SLEEP_MAP)
        if mapped:
            return mapped
    return None


def _map_skin_goal(doc: dict) -> SkinGoal | None:
    goals = _list_values(doc.get("skinGoals") or doc.get("skin_goals"))
    for item in goals:
        mapped = _map_optional_enum(item, _SKIN_GOAL_MAP)
        if mapped:
            return mapped
    return _map_optional_enum(doc.get("skinGoal") or doc.get("skin_goal"), _SKIN_GOAL_MAP)


_SKIN_TYPE_VALUES = [t.value for t in SkinType]


def _has_minimum_skin_profile(doc: dict) -> bool:
    """Same core fields Label Looker requires for a skincare scan."""
    return diagnose_skin_profile(doc).get("ready") is True


def diagnose_skin_profile(doc: dict | None) -> dict[str, Any]:
    """
    Explain why a merged profile document cannot be used for personalised HLHP alerts.
    Returns { ready, missing_fields, invalid_fields, message }.
    """
    missing: list[str] = []
    invalid: list[dict[str, Any]] = []

    if not doc:
        missing.extend(["age", "gender", "skin type", "skin concerns"])
        return _profile_diagnosis_result(missing=missing, invalid=invalid)

    age = _parse_age(doc.get("age"))
    age_bracket_raw = doc.get("ageBracket") or doc.get("age_bracket")
    has_age = age is not None or bool(age_bracket_raw)
    if not has_age:
        missing.append("age")
    elif _map_age_bracket(doc) is None:
        invalid.append(
            {
                "field": "age",
                "label": "age",
                "reason": "unrecognized_value",
                "value": doc.get("age") or age_bracket_raw,
                "hint": "Use a numeric age or a supported age bracket.",
            }
        )

    gender_raw = doc.get("gender")
    if not _scalar(gender_raw):
        missing.append("gender")
    elif _map_gender(gender_raw) is None:
        invalid.append(
            {
                "field": "gender",
                "label": "gender",
                "reason": "unrecognized_value",
                "value": _scalar(gender_raw),
                "accepted": [g.value for g in Gender],
            }
        )

    skin_type_raw = doc.get("skinType") or doc.get("skin_type")
    if not _scalar(skin_type_raw):
        missing.append("skin type")
    elif map_skin_type(_scalar(skin_type_raw) if skin_type_raw is not None else None) is None:
        invalid.append(
            {
                "field": "skinType",
                "label": "skin type",
                "reason": "unrecognized_value",
                "value": _scalar(skin_type_raw),
                "accepted": _SKIN_TYPE_VALUES,
            }
        )

    concerns_raw = _list_values(doc.get("skinConcerns") or doc.get("skin_concerns"))
    if not concerns_raw:
        missing.append("skin concerns")
    else:
        mapped = map_skin_concerns(concerns_raw)
        if not mapped:
            examples = ", ".join(supported_skin_concern_examples())
            invalid.append(
                {
                    "field": "skinConcerns",
                    "label": "skin concerns",
                    "reason": "unrecognized_values",
                    "value": concerns_raw,
                    "hint": (
                        "Choose at least one skin concern from your profile (e.g. "
                        f"{examples})."
                    ),
                }
            )

    return _profile_diagnosis_result(missing=missing, invalid=invalid)


def _profile_diagnosis_result(
    *,
    missing: list[str],
    invalid: list[dict[str, Any]],
) -> dict[str, Any]:
    ready = not missing and not invalid
    if ready:
        return {
            "ready": True,
            "missing_fields": [],
            "invalid_fields": [],
            "message": "",
        }

    invalid_labels = [str(item.get("label") or item.get("field") or "field") for item in invalid]

    if not missing and invalid:
        message = (
            "Your skin profile has values we could not use for personalised alerts. "
            f"Please update: {', '.join(invalid_labels)}."
        )
    elif missing and not invalid:
        message = (
            "Your skin profile is incomplete for personalised alerts. "
            f"Please add: {', '.join(missing)}."
        )
    else:
        message = (
            "Your skin profile is incomplete for personalised alerts. "
            f"Please add {', '.join(missing)} and fix {', '.join(invalid_labels)}."
        )

    return {
        "ready": False,
        "missing_fields": missing,
        "invalid_fields": invalid,
        "message": message,
    }


async def load_merged_profile_doc(
    user_id: str,
    *,
    auth_user: dict | None = None,
) -> dict:
    """Load merged user_details + users row with taxonomy labels resolved."""
    db = get_hlhp_db()
    users_coll = db[_USER_COLL]
    user_details_coll = db[_USER_DETAILS_COLL]

    mongo_user_id = await resolve_users_collection_id(
        users_coll=users_coll,
        user_id=user_id,
        auth_user=auth_user,
    )
    raw = await user_details_coll.find_one(
        user_details_lookup_filter(user_id, mongo_user_id=mongo_user_id)
    ) or {}
    normalized = normalize_mongo_profile_shape(raw)

    account = await users_coll.find_one(
        users_lookup_filter(user_id=user_id, auth_user=auth_user)
    )
    merged = normalized
    if account:
        merged = merge_auth_user_details(merged, dict(account))
    if auth_user:
        merged = merge_auth_user_details(merged, auth_user)

    if merged:
        await refresh_taxonomy_aliases_from_db()
        merged = await resolve_profile_taxonomy_refs(db, merged)
    return merged


def map_merged_doc_to_user_profile(user_id: str, doc: dict) -> UserProfile | None:
    if not _has_minimum_skin_profile(doc):
        return None

    skin_concerns = map_skin_concerns(
        _list_values(doc.get("skinConcerns") or doc.get("skin_concerns"))
    )
    if not skin_concerns:
        return None

    skin_type = map_skin_type(_scalar(doc.get("skinType") or doc.get("skin_type")))
    gender = _map_gender(doc.get("gender"))
    age_bracket = _map_age_bracket(doc)
    if not skin_type or not gender or not age_bracket:
        return None

    return UserProfile(
        user_id=user_id,
        skin_type=skin_type,
        skin_concerns=skin_concerns,
        gender=gender,
        age_bracket=age_bracket,
        life_stage=_map_life_stage(doc, gender=gender),
        skin_goal=_map_skin_goal(doc),
        smoking_status=_map_optional_enum(
            doc.get("smokingStatus") or doc.get("smoking_status"), _SMOKING_MAP
        ),
        stress_level=_map_optional_enum(
            doc.get("stressLevel") or doc.get("stress_level"), _STRESS_MAP
        ),
        sleep_time=_map_sleep_time(doc),
        hair_type=map_hair_type(_scalar(doc.get("hairType") or doc.get("hair_type"))),
        hair_concerns=map_hair_concerns(
            _list_values(doc.get("hairConcerns") or doc.get("hair_concerns"))
        ),
        skin_tone_fitzpatrick=_map_skin_tone_fitzpatrick(doc),
    )


async def load_user_profile(user_id: str, *, auth_user: dict | None = None) -> UserProfile | None:
    try:
        doc = await load_merged_profile_doc(user_id, auth_user=auth_user)
    except Exception as exc:
        logger.warning("HLHP: profile load failed for user_id=%s: %s", user_id, exc)
        return None

    profile = map_merged_doc_to_user_profile(user_id, doc)
    if profile is None:
        logger.info(
            "HLHP: incomplete skin profile for user_id=%s (no default fallback)",
            user_id,
        )
    return profile


async def load_user_first_name(user_id: str, *, auth_user: dict | None = None) -> str:
    try:
        doc = await load_merged_profile_doc(user_id, auth_user=auth_user)
    except Exception:
        return ""
    name = extract_first_name_from_doc(doc)
    if name:
        return name
    if auth_user:
        return extract_first_name_from_doc(auth_user)
    return ""


# Backward compat for coach module import
_user_details_lookup_filter = user_details_lookup_filter
