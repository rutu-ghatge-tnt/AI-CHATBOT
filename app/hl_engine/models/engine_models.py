"""
Unified engine data models (internal — not exposed via v1/v2 API).

A single response shape (EngineResponse) and a single entry-point signature
(evaluate(env, profile=None)) for the unified engine path.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SkinType(str, Enum):
    NORMAL = "normal"
    OILY = "oily"
    DRY = "dry"
    COMBINATION = "combination"
    SENSITIVE = "sensitive"


class SkinConcern(str, Enum):
    ACNE = "acne"
    MELASMA = "melasma"
    PIGMENTATION = "pigmentation"
    TAN = "tan"
    AGING = "aging"
    DULLNESS = "dullness"
    SENSITIVITY = "sensitivity"
    DEHYDRATION = "dehydration"
    REDNESS = "redness"
    DARK_CIRCLES = "dark_circles"
    PORES = "pores"
    TEXTURE = "texture"


class EnvironmentalData(BaseModel):
    location: str
    uv_index: float
    temperature_c: float
    aqi: int
    humidity_pct: float


class UserProfile(BaseModel):
    skin_type: Optional[SkinType] = None
    concerns: list[SkinConcern] = Field(default_factory=list)

    @property
    def primary_concern(self) -> Optional[SkinConcern]:
        return self.concerns[0] if self.concerns else None


class Alert(BaseModel):
    l1: str
    l2: str
    l3: str


class ScienceTip(BaseModel):
    fact: str
    source: str


class FactorBreakdown(BaseModel):
    uv: int
    temperature: int
    aqi: int
    humidity: int


class EngineResponse(BaseModel):
    skin_friendliness_index: int
    band: str
    band_color: str
    is_personalized: bool
    factor_breakdown: FactorBreakdown
    location: str
    readings: EnvironmentalData
    scenario_code: str
    scenario_name: str
    alert: Alert
    science_tip: ScienceTip
    profile_summary: str
