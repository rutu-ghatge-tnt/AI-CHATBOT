"""HLHP V4 prototype API models (7-tab client contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class V4Weather(BaseModel):
    temp_c: float
    uv_index: float
    humidity_pct: float
    aqi: int
    wind_kmh: float = 0.0
    wind_dir: str = ""
    gust_kmh: float = 0.0


class V4DriverOut(BaseModel):
    factor: str
    band: str
    points: int
    level: Literal["Low", "Medium", "High"]
    dominant: bool = False


class V4SfiOut(BaseModel):
    environmental: int
    personal: Optional[int] = None
    headline: int


class V4AlertEvidence(BaseModel):
    confidence: str = ""
    pmids: list[str] = Field(default_factory=list)


class V4AlertOut(BaseModel):
    level: Literal["L0", "L1", "L2"] = "L0"
    l0: str = ""
    l1: str = ""
    tip: str = ""
    evidence: V4AlertEvidence = Field(default_factory=V4AlertEvidence)


class V4TodayResponse(BaseModel):
    city: str
    date: str
    mode_of_use: Literal["personal", "guest"]
    weather: V4Weather
    scene: str
    drivers: list[V4DriverOut]
    sfi: V4SfiOut
    mode: str
    alert: V4AlertOut
    compound: Optional[str] = None
    surge: bool = False
    surge_tags: list[str] = Field(default_factory=list)


OutdoorExposure = Literal["in", "<1", "1-3", "3+"]


class V4LogRequest(BaseModel):
    user_id: str
    date: Optional[str] = None
    symptoms: list[str] = Field(min_length=1)
    areas: list[str] = Field(default_factory=list)
    local_time: Optional[datetime] = None
    city: str = ""
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    outdoor_exposure: Optional[OutdoorExposure] = None
    notes: Optional[str] = Field(None, max_length=500)
    doctor_id: Optional[str] = Field(default=None, alias="doctorId")
    selfie_url: Optional[str] = Field(default=None, alias="selfieUrl")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_symptoms(self):
        normalized = [s.strip().lower().replace(" ", "_") for s in self.symptoms if s.strip()]
        allowed = {"normal", "dry", "oily", "dull", "breakout", "spots"}
        unknown = [s for s in normalized if s not in allowed]
        if unknown:
            raise ValueError(f"Unknown symptoms: {', '.join(unknown)}")
        if "normal" in normalized and len(normalized) > 1:
            raise ValueError("'normal' is exclusive — remove other symptoms")
        areas = [a.strip().lower().replace(" ", "_") for a in self.areas if a.strip()]
        if "full_face" in areas and len(areas) > 1:
            raise ValueError("'full_face' is exclusive of specific zones")
        needs_area = {"breakout", "spots"}
        if needs_area.intersection(normalized) and not areas:
            raise ValueError("areas required for breakout / spots")
        return self


class V4LogResponse(BaseModel):
    streak: int
    log_days_30d: int
    patterns_unlock_in: int


class V4RecapDay(BaseModel):
    date: str
    sfi: Optional[int] = None
    dominant_driver: Optional[str] = None


class V4RecapResponse(BaseModel):
    month: str
    days: list[V4RecapDay] = Field(default_factory=list)
    event_callouts: list[dict[str, Any]] = Field(default_factory=list)
    verdict_vs_previous_month: Optional[str] = None
    avg_sfi: Optional[int] = None
    prev_month_avg_sfi: Optional[int] = None


class V4ShareResponse(BaseModel):
    week_start: str
    week_end: str
    week_avg: Optional[int] = None
    delta_vs_prev_7_days: Optional[int] = None
    daily_values: list[dict[str, Any]] = Field(default_factory=list)
    caption: str = ""


class V4LearnLeverOut(BaseModel):
    category: Literal["nutrition", "lifestyle"]
    label: str
    body: str


class V4LearnResponse(BaseModel):
    explainers: list[dict[str, Any]] = Field(default_factory=list)
    nuggets: list[dict[str, Any]] = Field(default_factory=list)
    levers: list[V4LearnLeverOut] = Field(default_factory=list)
    concern_id: Optional[str] = None
    city: Optional[str] = None
