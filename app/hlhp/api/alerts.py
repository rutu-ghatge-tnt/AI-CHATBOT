from fastapi import APIRouter, HTTPException, Query

from app.hlhp.models.alert import AlertResponse
from app.hlhp.services.alert_generator import generate_alert
from app.hlhp.services.scoring_engine import calculate_skin_score
from app.hlhp.services.weather_fetcher import fetch_environmental_data

router = APIRouter(prefix="/hl/v1", tags=["HLHP — Hyperlocal Health Profile (Guest)"])


@router.get("/alert", response_model=AlertResponse)
async def get_skin_alert(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude"),
):
    try:
        env_data = await fetch_environmental_data(lat, lng)
        skin_score = calculate_skin_score(env_data)
        return generate_alert(env_data, skin_score)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"HL alert generation failed: {exc}") from exc


@router.get("/score-only")
async def get_skin_score_only(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
):
    try:
        env_data = await fetch_environmental_data(lat, lng)
        score = calculate_skin_score(env_data)
        return {
            "score": score.total,
            "band": score.band.value,
            "location": env_data.location_name,
            "factors": {
                "uv": {"value": env_data.uv_index, "points": score.factors[0].points},
                "temp": {"value": env_data.temperature_c, "points": score.factors[1].points},
                "aqi": {"value": env_data.aqi, "points": score.factors[2].points},
                "humidity": {"value": env_data.humidity_pct, "points": score.factors[3].points},
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health-check")
async def health_check():
    return {"status": "healthy", "service": "hlhp", "version": "2.0.0"}

