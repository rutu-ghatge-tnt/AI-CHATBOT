import logging
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from app.hlhp.db import hl_db
from app.hlhp.models.personalized_alert import PersonalizedAlertResponse
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
from app.hlhp.services.alert_generator import generate_alert
from app.hlhp.services.profile_personalizer import personalize_alert
from app.hlhp.services.scoring_engine import calculate_skin_score
from app.hlhp.services.weather_fetcher import fetch_environmental_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hl/v2", tags=["HLHP — Hyperlocal Health Profile"])
user_details_col = hl_db["user_details"]


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

_HAIR_CONCERN_MAP = {
    "frizz": HairConcern.FRIZZ,
    "dandruff": HairConcern.DANDRUFF,
    "hair-loss": HairConcern.THINNING,
    "thinning": HairConcern.THINNING,
    "oily-scalp": HairConcern.OILINESS,
    "dryness": HairConcern.DRYNESS,
    "color-treated": HairConcern.COLOR_TREATED,
    "color_treated": HairConcern.COLOR_TREATED,
    "hair-breakage": HairConcern.BREAKAGE,
    "breakage": HairConcern.BREAKAGE,
    "sensitive-scalp": HairConcern.SCALP_SENSITIVITY,
    "scalp-sensitivity": HairConcern.SCALP_SENSITIVITY,
    "scalp_itchiness": HairConcern.SCALP_SENSITIVITY,
    "scalp-itchiness": HairConcern.SCALP_SENSITIVITY,
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
}


def _map_optional_enum(raw, mapping: dict):
    if not raw or not isinstance(raw, str):
        return None
    return mapping.get(raw.strip().lower())


_HAIR_TYPE_MAP = {
    "straight": HairType.STRAIGHT,
    "wavy": HairType.WAVY,
    "curly": HairType.CURLY,
    "coily": HairType.COILY,
    "thinning": HairType.THINNING,
}


def _normalize_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    for item in values:
        if isinstance(item, str):
            cleaned = item.strip().lower()
            if cleaned:
                normalized.append(cleaned)
    return normalized


def _map_skin_concerns(raw: list[str]) -> list[SkinConcern]:
    concerns = []
    for item in raw:
        mapped = _SKIN_CONCERN_MAP.get(item)
        if mapped and mapped not in concerns:
            concerns.append(mapped)
    return concerns[:3]


def _map_hair_concerns(raw: list[str]) -> list[HairConcern]:
    concerns = []
    for item in raw:
        mapped = _HAIR_CONCERN_MAP.get(item)
        if mapped and mapped not in concerns:
            concerns.append(mapped)
    return concerns[:3]


def _map_hair_type(raw: list[str]) -> HairType | None:
    if not raw:
        return None
    return _HAIR_TYPE_MAP.get(raw[0])


def _map_skin_type(raw_value: str | None) -> SkinType:
    if not raw_value:
        return SkinType.NORMAL
    normalized = raw_value.strip().lower()
    try:
        return SkinType(normalized)
    except ValueError:
        return SkinType.NORMAL


def _default_user_profile(user_id: str) -> UserProfile:
    """Same baseline as a partial Mongo row (see skin_concerns fallback below)."""
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
    """Match common shapes: camelCase userId, snake_case user_id, ObjectId, document _id."""
    clauses: list[dict] = [
        {"userId": user_id},
        {"user_id": user_id},
    ]
    if ObjectId.is_valid(user_id):
        oid = ObjectId(user_id)
        clauses.extend(({"userId": oid}, {"_id": oid}))
    return {"$or": clauses}


async def _get_user_profile(user_id: str) -> UserProfile:
    """
    Load profile from `skin_bb.user_details`.
    Supports string/ObjectId userId, snake_case user_id, and legacy _id lookups.
    If no document exists (common when local Mongo is empty but dev is not), use defaults
    instead of failing the whole alert.
    """
    doc = await user_details_col.find_one(_user_details_lookup_filter(user_id))
    if not doc:
        logger.warning(
            "HLHP personalized alert: no user_details row for user_id=%s; using default profile",
            user_id,
        )
        return _default_user_profile(user_id)

    skin_type = _map_skin_type(doc.get("skinType"))
    skin_concerns = _map_skin_concerns(_normalize_list(doc.get("skinConcerns")))
    if not skin_concerns:
        # Keep personalization resilient even if source profile is partial.
        skin_concerns = [SkinConcern.SENSITIVITY]

    hair_type = _map_hair_type(_normalize_list(doc.get("hairType")))
    hair_concerns = _map_hair_concerns(_normalize_list(doc.get("hairConcerns")))

    gender_raw = doc.get("gender") or doc.get("Gender")
    gender = Gender.OTHER
    if isinstance(gender_raw, str):
        try:
            gender = Gender(gender_raw.strip().lower().replace("-", "_"))
        except ValueError:
            gender = Gender.OTHER

    age_raw = doc.get("ageBracket") or doc.get("age_bracket")
    age_bracket = AgeBracket.AGE_25_30
    if isinstance(age_raw, str):
        try:
            age_bracket = AgeBracket(age_raw.strip())
        except ValueError:
            age_bracket = AgeBracket.AGE_25_30

    return UserProfile(
        user_id=user_id,
        skin_type=skin_type,
        skin_concerns=skin_concerns,
        gender=gender,
        age_bracket=age_bracket,
        skin_goal=_map_optional_enum(doc.get("skinGoal") or doc.get("skin_goal"), _SKIN_GOAL_MAP),
        smoking_status=_map_optional_enum(doc.get("smokingStatus") or doc.get("smoking_status"), _SMOKING_MAP),
        stress_level=_map_optional_enum(doc.get("stressLevel") or doc.get("stress_level"), _STRESS_MAP),
        sleep_time=_map_optional_enum(doc.get("sleepTime") or doc.get("sleep_time"), _SLEEP_MAP),
        hair_type=hair_type,
        hair_concerns=hair_concerns,
    )


@router.get("/alert", response_model=PersonalizedAlertResponse)
async def get_personalized_alert(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    user_id: str = Query(...),
):
    try:
        env_data = await fetch_environmental_data(lat, lng)
        score = calculate_skin_score(env_data)
        generic_alert = generate_alert(env_data, score)
        profile = await _get_user_profile(user_id)
        return personalize_alert(generic_alert, profile, env_data, score)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Personalized HLHP generation failed: {exc}") from exc


@router.get("/alert/preview", response_model=PersonalizedAlertResponse)
async def preview_personalized_alert(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    skin_type: SkinType = Query(...),
    primary_concern: SkinConcern = Query(...),
    gender: Gender = Query(Gender.OTHER),
    age_bracket: AgeBracket = Query(AgeBracket.AGE_25_30),
    hair_type: HairType | None = Query(None),
    hair_concern: HairConcern | None = Query(None),
):
    try:
        profile = UserProfile(
            user_id="preview",
            skin_type=skin_type,
            skin_concerns=[primary_concern],
            gender=gender,
            age_bracket=age_bracket,
            hair_type=hair_type,
            hair_concerns=[hair_concern] if hair_concern else [],
        )
        env_data = await fetch_environmental_data(lat, lng)
        score = calculate_skin_score(env_data)
        generic_alert = generate_alert(env_data, score)
        return personalize_alert(generic_alert, profile, env_data, score)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {exc}") from exc
