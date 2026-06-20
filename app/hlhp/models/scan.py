"""HLHP v2 scan API models (spec §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

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

    @model_validator(mode="after")
    def require_env_source(self):
        has_coords = self.latitude is not None and self.longitude is not None
        has_raw = all(
            v is not None for v in (self.raw_uvi, self.raw_aqi, self.raw_rh, self.raw_temp)
        )
        if not has_coords and not has_raw:
            raise ValueError("Provide latitude/longitude or all raw env readings")
        return self


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


class ScanResponse(BaseModel):
    snapshot_version: str
    workbook_version: Optional[str] = None
    mode: Literal["personalised", "guest"]
    env_snapshot: EnvSnapshot
    outdoor_ok_score: int
    outdoor_ok_band_text: str
    mood_verdict_today: str
    mood_headline: Optional[str] = None
    forecast_oneliner: Optional[str] = None
    sudden_event_tags: list[str] = Field(default_factory=list)
    alert_count_label: Optional[str] = None
    symptom_chips: list[SymptomChip] = Field(default_factory=list)
    lane_state_ctas: dict[str, str] = Field(default_factory=dict)
    sfi_factor_cards: list[SfiFactorCard] = Field(default_factory=list)
    alerts: list[AlertTile]
    candidate_alerts: list[AlertTile] = Field(default_factory=list)
    science_nugget: Optional[ScienceNuggetOut] = None
    profile_nudge: Optional[str] = None


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


class HealthResponse(BaseModel):
    ok: bool
    snapshot_version: str
    workbook_version: Optional[str] = None
    rule_count: int
    composition_row_count: int = 0
    generated_at: str
