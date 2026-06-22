"""Load user profile from Mongo (users + user_details) for HLHP personalisation.

Uses the same merge + taxonomy resolution path as Label Looker so externalId
auth ids (e.g. 6a32a1ef9e214d0b3780c0c5) resolve to the correct user_details row.
"""

from __future__ import annotations

import logging
import os
import re

from app.hlhp.db import get_hlhp_db
from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    HairConcern,
    HairType,
    SkinConcern,
    SkinGoal,
    SkinType,
    SleepTime,
    SmokingStatus,
    StressLevel,
    UserProfile,
)
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

_SKIN_CONCERN_MAP = {
    "sensitive": SkinConcern.SENSITIVITY,
    "sensitivity": SkinConcern.SENSITIVITY,
    "acne": SkinConcern.ACNE,
    "oiliness": SkinConcern.PORES,
    "oily": SkinConcern.PORES,
    "pigmentation": SkinConcern.PIGMENTATION,
    "tan": SkinConcern.TAN,
    "aging": SkinConcern.AGING,
    "dullness": SkinConcern.DULLNESS,
    "dark-circles": SkinConcern.DARK_CIRCLES,
    "dark_circles": SkinConcern.DARK_CIRCLES,
    "dark circles": SkinConcern.DARK_CIRCLES,
    "sleep-deprivation": SkinConcern.DARK_CIRCLES,
    "pores": SkinConcern.PORES,
    "texture": SkinConcern.TEXTURE,
    "dehydration": SkinConcern.DEHYDRATION,
    "dryness": SkinConcern.DEHYDRATION,
    "redness": SkinConcern.REDNESS,
    "melasma": SkinConcern.MELASMA,
    "pih": SkinConcern.PIGMENTATION,
}

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

_HAIR_CONCERN_MAP = {
    "frizz": HairConcern.FRIZZ,
    "dandruff": HairConcern.DANDRUFF,
    "hair-fall": HairConcern.THINNING,
    "hair_fall": HairConcern.THINNING,
    "thinning": HairConcern.THINNING,
    "oiliness": HairConcern.OILINESS,
    "dryness": HairConcern.DRYNESS,
    "color-treated": HairConcern.COLOR_TREATED,
    "color_treated": HairConcern.COLOR_TREATED,
    "breakage": HairConcern.BREAKAGE,
    "scalp-sensitivity": HairConcern.SCALP_SENSITIVITY,
    "scalp_sensitivity": HairConcern.SCALP_SENSITIVITY,
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


def _map_skin_concerns(raw_values: list[str]) -> list[SkinConcern]:
    concerns: list[SkinConcern] = []
    for item in raw_values:
        key = _norm_key(item)
        mapped = _SKIN_CONCERN_MAP.get(key) or _SKIN_CONCERN_MAP.get(key.replace("-", "_"))
        if mapped and mapped not in concerns:
            concerns.append(mapped)
    return concerns[:3]


def _map_skin_type(raw_value: str | None) -> SkinType | None:
    scalar = _scalar(raw_value)
    if not scalar or not isinstance(scalar, str):
        return None
    try:
        return SkinType(scalar.strip().lower())
    except ValueError:
        return None


def _map_hair_type(raw_value: str | None) -> HairType | None:
    scalar = _scalar(raw_value)
    if not scalar or not isinstance(scalar, str):
        return None
    try:
        return HairType(scalar.strip().lower())
    except ValueError:
        return None


def _map_hair_concerns(raw_values: list[str]) -> list[HairConcern]:
    out: list[HairConcern] = []
    for item in raw_values:
        key = _norm_key(item)
        mapped = _HAIR_CONCERN_MAP.get(key)
        if mapped and mapped not in out:
            out.append(mapped)
    return out[:3]


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


def _has_minimum_skin_profile(doc: dict) -> bool:
    """Same core fields Label Looker requires for a skincare scan."""
    if not doc:
        return False
    age = _parse_age(doc.get("age"))
    age_bracket = doc.get("ageBracket") or doc.get("age_bracket")
    gender = _scalar(doc.get("gender"))
    skin_type = _scalar(doc.get("skinType") or doc.get("skin_type"))
    concerns = _list_values(doc.get("skinConcerns") or doc.get("skin_concerns"))
    has_age = age is not None or bool(age_bracket)
    return bool(has_age and gender and skin_type and concerns)


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
        merged = await resolve_profile_taxonomy_refs(db, merged)
    return merged


def map_merged_doc_to_user_profile(user_id: str, doc: dict) -> UserProfile | None:
    if not _has_minimum_skin_profile(doc):
        return None

    skin_concerns = _map_skin_concerns(
        _list_values(doc.get("skinConcerns") or doc.get("skin_concerns"))
    )
    if not skin_concerns:
        return None

    skin_type = _map_skin_type(doc.get("skinType") or doc.get("skin_type"))
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
        skin_goal=_map_skin_goal(doc),
        smoking_status=_map_optional_enum(
            doc.get("smokingStatus") or doc.get("smoking_status"), _SMOKING_MAP
        ),
        stress_level=_map_optional_enum(
            doc.get("stressLevel") or doc.get("stress_level"), _STRESS_MAP
        ),
        sleep_time=_map_sleep_time(doc),
        hair_type=_map_hair_type(doc.get("hairType") or doc.get("hair_type")),
        hair_concerns=_map_hair_concerns(
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
    for key in ("firstName", "first_name", "name", "displayName", "userName", "username"):
        val = doc.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().split()[0]
    return ""


# Backward compat for coach module import
_user_details_lookup_filter = user_details_lookup_filter
