import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.hlhp.api.deps_auth import hlhp_authenticated_user, user_id_from_auth
from app.hlhp.models.personalized_alert import PersonalizedAlertResponse
from app.hlhp.models.profile import (
    AgeBracket,
    Gender,
    HairConcern,
    HairType,
    SkinConcern,
    SkinType,
    UserProfile,
)
from app.hlhp.services.alert_generator import generate_alert
from app.hlhp.services.profile_loader import load_user_profile
from app.hlhp.services.profile_personalizer import personalize_alert
from app.hlhp.services.scoring_engine import calculate_skin_score
from app.hlhp.services.weather_fetcher import fetch_environmental_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hl/v2", tags=["HLHP — Hyperlocal Health Profile"])


@router.get("/alert", response_model=PersonalizedAlertResponse)
async def get_personalized_alert(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    user: dict[str, Any] = Depends(hlhp_authenticated_user),
):
    try:
        env_data = await fetch_environmental_data(lat, lng)
        score = calculate_skin_score(env_data)
        generic_alert = generate_alert(env_data, score)
        user_id = user_id_from_auth(user)
        profile = await load_user_profile(user_id, auth_user=user)
        if profile is None:
            raise HTTPException(
                status_code=400,
                detail="Skin profile incomplete — add age, gender, skin type, and concerns in your account.",
            )
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
