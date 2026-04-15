from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query

from app.ai_ingredient_intelligence.db.mongodb import db
from app.hl_engine.models.personalized_alert import PersonalizedAlertResponse
from app.hl_engine.models.profile import (
    AgeBracket,
    Gender,
    HairConcern,
    HairType,
    SkinConcern,
    SkinType,
    UserProfile,
)
from app.hl_engine.services.alert_generator import generate_alert
from app.hl_engine.services.profile_personalizer import personalize_alert
from app.hl_engine.services.scoring_engine import calculate_skin_score
from app.hl_engine.services.weather_fetcher import fetch_environmental_data

router = APIRouter(prefix="/hl/v2", tags=["HLHP Personalized Alerts"])
user_details_col = db["user_details"]


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


async def _get_user_profile(user_id: str) -> UserProfile:
    """
    Load profile from `skin_bb.user_details`.
    Supports both ObjectId and string userId storage.
    """
    query = {"$or": [{"userId": user_id}]}
    if ObjectId.is_valid(user_id):
        query["$or"].append({"userId": ObjectId(user_id)})

    doc = await user_details_col.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Profile not found for user_id={user_id}")

    skin_type = _map_skin_type(doc.get("skinType"))
    skin_concerns = _map_skin_concerns(_normalize_list(doc.get("skinConcerns")))
    if not skin_concerns:
        # Keep personalization resilient even if source profile is partial.
        skin_concerns = [SkinConcern.SENSITIVITY]

    hair_type = _map_hair_type(_normalize_list(doc.get("hairType")))
    hair_concerns = _map_hair_concerns(_normalize_list(doc.get("hairConcerns")))

    return UserProfile(
        user_id=user_id,
        skin_type=skin_type,
        skin_concerns=skin_concerns,
        gender=Gender.OTHER,
        age_bracket=AgeBracket.AGE_25_30,
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
