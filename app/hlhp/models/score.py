from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SeverityBand(str, Enum):
    PARADISE = "Paradise Mode"
    SMOOTH = "Smooth Sailing"
    GUARD = "Guard Up"
    BATTLE = "Battle Stations"
    HOSTILE = "Hostile Mode"
    CODE_RED = "Code Red"


class FactorScore(BaseModel):
    factor: Literal["uv_index", "temperature", "aqi", "humidity"]
    raw_value: float
    points: int = Field(..., ge=0, le=25)
    label: str
    alert_level: str
    skin_impact: str


class SkinScore(BaseModel):
    total: int = Field(..., ge=0, le=100)
    band: SeverityBand
    band_raw: SeverityBand
    override_applied: bool = False
    override_reason: str = ""
    factors: list[FactorScore]
    dominant_threat: str
    secondary_threats: list[str]

