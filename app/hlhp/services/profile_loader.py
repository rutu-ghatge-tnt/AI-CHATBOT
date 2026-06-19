"""Load user profile from Mongo user_details for HLHP personalisation."""

from __future__ import annotations

import logging

from bson import ObjectId

from app.hlhp.db import hl_db
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

logger = logging.getLogger(__name__)

_SKIN_CONCERN_MAP = {
    "sensitive": SkinConcern.SENSITIVITY,
    "acne": SkinConcern.ACNE,
    "oiliness": SkinConcern.PORES,
    "pigmentation": SkinConcern.PIGMENTATION,
    "tan": SkinConcern.TAN,
    "aging": SkinConcern.AGING,
    "dullness": SkinConcern.DULLNESS,
    "dark-circles": SkinConcern.DARK_CIRCLES,
    "dark_circles": SkinConcern.DARK_CIRCLES,
    "pores": SkinConcern.PORES,
    "texture": SkinConcern.TEXTURE,
    "dehydration": SkinConcern.DEHYDRATION,
    "redness": SkinConcern.REDNESS,
    "melasma": SkinConcern.MELASMA,
}

_SKIN_GOAL_MAP = {
    "prevention": SkinGoal.PREVENTION,
    "barrier_health": SkinGoal.BARRIER_HEALTH,
    "barrier-health": SkinGoal.BARRIER_HEALTH,
    "brightening": SkinGoal.BRIGHTENING,
    "anti_aging": SkinGoal.ANTI_AGING,
    "anti-aging": SkinGoal.ANTI_AGING,
    "acne_control": SkinGoal.ACNE_CONTROL,
    "acne-control": SkinGoal.ACNE_CONTROL,
    "hydration": SkinGoal.HYDRATION,
    "even_tone": SkinGoal.EVEN_TONE,
    "even-tone": SkinGoal.EVEN_TONE,
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
    "5_6h": SleepTime.H5_6H,
    "5-6h": SleepTime.H5_6H,
    "6_7h": SleepTime.H6_7H,
    "6-7h": SleepTime.H6_7H,
    "7_9h": SleepTime.H7_9H,
    "7-9h": SleepTime.H7_9H,
    "more_than_9h": SleepTime.MORE_THAN_9H,
    "more-than-9h": SleepTime.MORE_THAN_9H,
    "under_6h": SleepTime.LESS_THAN_5H,
    "6_7h_v2": SleepTime.H6_7H,
    "7_8h": SleepTime.H7_9H,
    "over_8h": SleepTime.MORE_THAN_9H,
}


def _map_optional_enum(raw, mapping: dict):
    if not raw or not isinstance(raw, str):
        return None
    return mapping.get(raw.strip().lower())


def _normalize_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    return [item.strip().lower() for item in values if isinstance(item, str) and item.strip()]


def _map_skin_concerns(raw: list[str]) -> list[SkinConcern]:
    concerns = []
    for item in raw:
        mapped = _SKIN_CONCERN_MAP.get(item)
        if mapped and mapped not in concerns:
            concerns.append(mapped)
    return concerns[:3]


def _map_skin_type(raw_value: str | None) -> SkinType:
    if not raw_value:
        return SkinType.NORMAL
    try:
        return SkinType(raw_value.strip().lower())
    except ValueError:
        return SkinType.NORMAL


def _default_user_profile(user_id: str) -> UserProfile:
    return UserProfile(
        user_id=user_id,
        skin_type=SkinType.NORMAL,
        skin_concerns=[SkinConcern.SENSITIVITY],
        gender=Gender.OTHER,
        age_bracket=AgeBracket.AGE_25_30,
        hair_type=None,
        hair_concerns=[],
    )


def _user_details_lookup_filter(user_id: str) -> dict:
    clauses: list[dict] = [{"userId": user_id}, {"user_id": user_id}]
    if ObjectId.is_valid(user_id):
        oid = ObjectId(user_id)
        clauses.extend(({"userId": oid}, {"_id": oid}))
    return {"$or": clauses}


async def load_user_profile(user_id: str) -> UserProfile:
    doc = await hl_db["user_details"].find_one(_user_details_lookup_filter(user_id))
    if not doc:
        logger.warning("HLHP: no user_details for user_id=%s; using default profile", user_id)
        return _default_user_profile(user_id)

    skin_concerns = _map_skin_concerns(_normalize_list(doc.get("skinConcerns")))
    if not skin_concerns:
        skin_concerns = [SkinConcern.SENSITIVITY]

    gender_raw = doc.get("gender") or doc.get("Gender")
    gender = Gender.OTHER
    if isinstance(gender_raw, str):
        try:
            gender = Gender(gender_raw.strip().lower().replace("-", "_"))
        except ValueError:
            gender = Gender.OTHER

    age_bracket = AgeBracket.AGE_25_30
    age_raw = doc.get("ageBracket") or doc.get("age_bracket")
    if isinstance(age_raw, str):
        try:
            age_bracket = AgeBracket(age_raw.strip())
        except ValueError:
            age_bracket = AgeBracket.AGE_25_30

    return UserProfile(
        user_id=user_id,
        skin_type=_map_skin_type(doc.get("skinType")),
        skin_concerns=skin_concerns,
        gender=gender,
        age_bracket=age_bracket,
        skin_goal=_map_optional_enum(doc.get("skinGoal") or doc.get("skin_goal"), _SKIN_GOAL_MAP),
        smoking_status=_map_optional_enum(
            doc.get("smokingStatus") or doc.get("smoking_status"), _SMOKING_MAP
        ),
        stress_level=_map_optional_enum(doc.get("stressLevel") or doc.get("stress_level"), _STRESS_MAP),
        sleep_time=_map_optional_enum(doc.get("sleepTime") or doc.get("sleep_time"), _SLEEP_MAP),
        hair_type=None,
        hair_concerns=[],
    )
