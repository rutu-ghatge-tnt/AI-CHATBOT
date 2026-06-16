from typing import Optional

from pydantic import BaseModel

from app.hlhp.models.score import SkinScore


class ProtectionStep(BaseModel):
    step_number: int
    action: str
    reason: str
    product_category: str


class EvidenceAlertCard(BaseModel):
    id: str
    factor: str
    l1_text: str
    priority: str
    india_relevant: bool = False


class ScienceNuggetCard(BaseModel):
    id: int
    text: str
    factor: str
    source: str


class GapConflictCard(BaseModel):
    id: int
    type: str
    topic: str
    note: str = ""


class CoverageThinCell(BaseModel):
    grid: str
    trigger: str
    column: str
    computed_count: int = 0
    status: str


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
    # HLHP spec metadata (additive)
    profile_mode: Optional[str] = "guest"
    indian_season: Optional[str] = None
    environment_bands: Optional[dict[str, str]] = None
    # Evidence workbook metadata (additive — all 12 sheets)
    evidence_version: Optional[int] = None
    evidence_primary_id: Optional[str] = None
    evidence_carousel: Optional[list[EvidenceAlertCard]] = None
    habit_alerts: Optional[list[EvidenceAlertCard]] = None
    science_nuggets: Optional[list[ScienceNuggetCard]] = None
    clinical_gaps: Optional[list[GapConflictCard]] = None
    coverage_thin_cells: Optional[list[CoverageThinCell]] = None

