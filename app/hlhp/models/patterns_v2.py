"""Pydantic models for Patterns tab v2 API (v4 UI contract)."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class PatternChartPoint(BaseModel):
    lvl: float
    sym: bool


class PatternCardV2(BaseModel):
    id: str
    color_var: str
    w_icon: str
    w_label: str
    s_icon: str
    s_label: str
    driver_leg: str
    sym_leg: str
    say: str
    plain: str
    cc_note: str
    conf: int = Field(ge=1, le=5)
    label: str
    score_line: str
    chart: list[PatternChartPoint] = Field(default_factory=list)
    pmids: list[str] = Field(default_factory=list)
    status: str
    subscribed: bool = False
    src: str


class EmergingPatternV2(BaseModel):
    id: str
    text: str


class GenericCityPatternV2(BaseModel):
    city: str
    kick: str
    body: str
    factor: str
    color_var: str
    w_icon: str
    source: str


class UnlockCelebrationV2(BaseModel):
    headline: str
    stats: str
    log_days: int
    pattern_count: int


class PatternsMeterV2(BaseModel):
    log_days: int
    log_days_target: int
    exposure_days: int
    exposure_target: int
    days_since_first_log: int
    floor_days: int
    projected_unlock_date: Optional[str] = None


class ReactivationProgressV2(BaseModel):
    done: int
    need: int
    window: int
    reactivated: bool


FreshnessKind = Literal["active", "fading", "paused"]


class PatternsPayloadV2(BaseModel):
    state: str
    stability_partial: bool = False
    meter: PatternsMeterV2
    freshness: Optional[FreshnessKind] = None
    patterns: list[PatternCardV2] = Field(default_factory=list)
    emerging: list[EmergingPatternV2] = Field(default_factory=list)
    generic_city_pattern: Optional[GenericCityPatternV2] = None
    unlock_celebration: Optional[UnlockCelebrationV2] = None
    decay_banner: Optional[str] = None
    reactivation: Optional[ReactivationProgressV2] = None
    workbook_version: Optional[str] = None
    message: Optional[str] = None


class PatternsStateResponseV2(BaseModel):
    state: str
    stability_partial: bool = False
    meter: PatternsMeterV2
    freshness: Optional[FreshnessKind] = None
    reactivation: Optional[ReactivationProgressV2] = None


class PatternNarrationCard(BaseModel):
    id: str
    say: str = ""
    plain: str = ""
    cc_note: str = ""


class PatternsNarrationResponse(BaseModel):
    patterns: list[PatternNarrationCard] = Field(default_factory=list)
    unlock_headline: Optional[str] = None
    unlock_identity: Optional[str] = None
    weekly_digest: Optional[str] = None


class PatternAlertToggleRequest(BaseModel):
    user_id: str
    pattern_id: str
    on: bool = True


class PatternAlertToggleResponse(BaseModel):
    pattern_id: str
    subscribed: bool
    error: Optional[str] = None


class PatternPushTokenRequest(BaseModel):
    user_id: str
    token: str
    platform: str = "web"
