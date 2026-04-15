from typing import Optional

from pydantic import BaseModel

from app.hl_engine.models.score import SkinScore


class ProtectionStep(BaseModel):
    step_number: int
    action: str
    reason: str
    product_category: str


class AlertResponse(BaseModel):
    location_name: str
    uv_index: float
    temperature_c: float
    aqi: int
    humidity_pct: float
    skin_score: SkinScore
    compact_headline: str
    score_badge: str
    expand_cta: str
    whats_happening: str
    alert_body: str
    protection_steps: list[ProtectionStep]
    key_dont: str
    evening_recovery: str
    weekly_boost: str
    science_fact: str
    science_source: str
    scenario_code: str
    scenario_number: int
    health_advisory: Optional[str] = None
    color_code: str
    icon: str
    generated_at: str
    data_freshness_minutes: int
    weather_api_url: str
    raw_weather_payload: dict

