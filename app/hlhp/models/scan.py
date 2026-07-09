"""HLHP v2 scan API models (spec §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.hlhp.coach.models import CoachWrap

Severity = Literal["BLOCK_ENV", "HARD_ENV", "SOFT_ENV"]
PhaseUsed = Literal["morning_prep", "evening_recovery"]


class ScanRequest(BaseModel):
    user_id: Optional[str] = None
    city: str
    local_time: datetime
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    raw_uvi: Optional[float] = Field(None, ge=0)
    raw_aqi: Optional[int] = Field(None, ge=0)
    raw_rh: Optional[float] = Field(None, ge=0, le=100)
    raw_temp: Optional[float] = None
    force_surge: bool = False

    @model_validator(mode="after")
    def require_env_source(self):
        has_coords = self.latitude is not None and self.longitude is not None
        has_raw = all(
            v is not None for v in (self.raw_uvi, self.raw_aqi, self.raw_rh, self.raw_temp)
        )
        if not has_coords and not has_raw:
            raise ValueError("Provide latitude/longitude or all raw env readings")
        return self


class WeatherScreenVariant(BaseModel):
    screen: Optional[str] = None
    weather_type: Optional[str] = None
    background_image: Optional[str] = None
    animal_image: Optional[str] = None


class WeatherVisuals(BaseModel):
    weather_type: Optional[str] = None
    skin_care_tip: Optional[str] = None
    screen_variants: list[WeatherScreenVariant] = Field(default_factory=list)


class EnvSnapshot(BaseModel):
    user_id: Optional[str] = None
    city: str
    timestamp: str
    uvi: float
    aqi_cpcb: int
    rh_pct: float
    temp_c: float
    season: str
    uvi_band: str
    aqi_band: str
    rh_band: str
    temp_band: str


class AlertTile(BaseModel):
    rule_id: str
    severity: Severity
    l1: str
    l2: str
    phase_used: PhaseUsed
    mood_verdict_tag: str
    engagement_archetype: str
    symptom_keyword: Optional[str] = None
    routine_action: str = ""
    how_text: Optional[str] = None
    did_you_know: Optional[str] = None
    visual_icon_hint: str = ""
    physical_analogy: Optional[str] = None
    body_sensation_decode: Optional[str] = None
    source_citation: str
    factor: str = ""
    coach_wrap: Optional[CoachWrap] = None


class ScienceNuggetOut(BaseModel):
    id: int
    text: str
    factor: str
    source: str


class SymptomChip(BaseModel):
    keyword: str
    highlighted: bool = False


class SfiFactorCard(BaseModel):
    factor: str
    label: str
    skin_impact: str
    severity_pct: int = 0


SeverityBandName = Literal[
    "Paradise Mode",
    "Smooth Sailing",
    "Guard Up",
    "Battle Stations",
    "Hostile Mode",
    "Code Red",
]


class FlashAlertOut(BaseModel):
    level: Literal["L0", "L1"]
    mode: SeverityBandName
    l0: str
    l1: str
    tip: str


class ImpactLineOut(BaseModel):
    driver: Literal["temp", "uv", "humidity", "aqi"]
    name: str
    level: Literal["Low", "Medium", "High"]
    value: float


class EvidenceCellOut(BaseModel):
    id: str
    factor: str
    band: str
    evidence: str
    pmids: list[str] = Field(default_factory=list)
    confidence: str
    action: str = ""


class ScanResponse(BaseModel):
    snapshot_version: str
    workbook_version: Optional[str] = None
    mode: Literal["personalised", "guest"]
    concern_id: Optional[str] = None
    env_snapshot: EnvSnapshot
    outdoor_ok_score: int
    outdoor_ok_band_text: str
    mood_verdict_today: str
    mood_headline: Optional[str] = None
    strip_headline: Optional[str] = None
    forecast_oneliner: Optional[str] = None
    sudden_event_tags: list[str] = Field(default_factory=list)
    alert_count_label: Optional[str] = None
    symptom_chips: list[SymptomChip] = Field(default_factory=list)
    lane_state_ctas: dict[str, str] = Field(default_factory=dict)
    sfi_factor_cards: list[SfiFactorCard] = Field(default_factory=list)
    alerts: list[AlertTile]
    candidate_alerts: list[AlertTile] = Field(default_factory=list)
    user_first_name: Optional[str] = None
    science_nugget: Optional[ScienceNuggetOut] = None
    profile_nudge: Optional[str] = None
    weather_visuals: Optional[WeatherVisuals] = None
    skin_care_tip: Optional[str] = None
    weather_api_url: Optional[str] = None
    raw_weather_payload: Optional[dict[str, Any]] = None
    # v3.5 scenario library (SkinBB_HLHP_Scenario_Library_v3.5.xlsx)
    sfi: Optional[int] = None
    personal_sfi: Optional[int] = None
    band: Optional[SeverityBandName] = None
    action_cluster: Optional[str] = None
    risk: Optional[int] = None
    risk_label: Optional[str] = None
    confidence: Optional[str] = None
    flash_alert: Optional[FlashAlertOut] = None
    impacts: list[ImpactLineOut] = Field(default_factory=list)
    evidence_cell: Optional[EvidenceCellOut] = None
    scenario_library_version: Optional[str] = None
    time_window: Optional[Literal["morning", "daytime", "evening"]] = None
    scene: Optional[str] = None


class SymptomTapRequest(BaseModel):
    user_id: Optional[str] = None
    symptom_keyword: str
    city: str
    local_time: datetime
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    raw_uvi: Optional[float] = Field(None, ge=0)
    raw_aqi: Optional[int] = Field(None, ge=0)
    raw_rh: Optional[float] = Field(None, ge=0, le=100)
    raw_temp: Optional[float] = None


class SymptomTapResponse(BaseModel):
    headline: str
    decode_text: str
    tip: str
    source_locator: str
    matched_rules: list[AlertTile] = Field(default_factory=list)
    continuity_acknowledgment: Optional[str] = None


class SymptomFeelingRequest(BaseModel):
    user_id: str
    symptom_keyword: str
    local_time: datetime
    selected: bool = True


class SymptomFeelingResponse(BaseModel):
    symptom_keyword: str
    selected: bool
    selected_keywords: list[str] = Field(default_factory=list)


class FeelingLogStatusOut(BaseModel):
    can_log: bool = True
    cooldown_hours: int = 5
    next_log_at: Optional[str] = None
    retry_after_seconds: Optional[int] = None


class SymptomSelectedResponse(BaseModel):
    user_id: str
    selected_keywords: list[str] = Field(default_factory=list)
    areas: list[str] = Field(
        default_factory=list,
        description="Face areas from the latest log on the requested date",
    )
    feeling_log: FeelingLogStatusOut = Field(
        default_factory=FeelingLogStatusOut,
        description="Whether a new committed feeling session can be saved now",
    )


class HealthResponse(BaseModel):
    ok: bool
    snapshot_version: str
    workbook_version: Optional[str] = None
    rule_count: int
    composition_row_count: int = 0
    generated_at: str
    scenario_library_version: Optional[str] = None
    scenario_master_cells: int = 0
    scenario_compound_cells: int = 0
