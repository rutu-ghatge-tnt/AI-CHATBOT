"""SFI intraday timeline models (history + forecast slots)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SfiTimelineSource = Literal["history", "forecast"]
SfiTimelineMode = Literal["guest", "personalised"]


class SfiTimelinePoint(BaseModel):
    at: str
    at_epoch: int
    day_offset: int
    slot_hour: int
    source: SfiTimelineSource
    temp_c: float
    aqi: int
    uv_index: float
    humidity_pct: float
    sfi_env: int
    sfi: int


class SfiScanOverlayPoint(BaseModel):
    at: str
    at_epoch: int
    sfi_observed: int
    source: Literal["scan_log"] = "scan_log"


class SfiTimelineResponse(BaseModel):
    profile_curve_active: bool = False
    mode: SfiTimelineMode
    timezone: str
    slot_hours: list[int] = Field(default_factory=lambda: [6, 9, 12, 15, 18, 21])
    days_back: int
    days_ahead: int
    location_name: str = ""
    points: list[SfiTimelinePoint] = Field(default_factory=list)
    scan_overlays: list[SfiScanOverlayPoint] = Field(default_factory=list)
    forecast_source: str = "unavailable"
    workbook_version: str = ""
