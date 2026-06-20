"""HLHP history, catch-up, and consent API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SuddenEventEntry(BaseModel):
    date: str
    days_ago: int
    tag: str
    headline: str
    detail: str = ""


class SfiTrendPoint(BaseModel):
    date: str
    sfi: int
    sudden_event: bool = False


class MostFiredMood(BaseModel):
    mood: str
    display: str
    days_count: int


class ReturnerBanner(BaseModel):
    show: bool = False
    days_away: int = 0
    headline: str = ""
    context: str = ""


class HistoryResponse(BaseModel):
    user_id: str
    days: int
    scan_count: int = 0
    sfi_average: Optional[float] = None
    sfi_prior_period_average: Optional[float] = None
    sfi_delta_vs_prior: Optional[float] = None
    sudden_events: list[SuddenEventEntry] = Field(default_factory=list)
    trend: list[SfiTrendPoint] = Field(default_factory=list)
    most_fired_mood: Optional[MostFiredMood] = None
    returner_banner: Optional[ReturnerBanner] = None
    message: Optional[str] = None
    workbook_version: Optional[str] = None


class CatchupResponse(BaseModel):
    user_id: str
    paragraphs: list[str] = Field(default_factory=list)
    generated_at: str
    workbook_version: Optional[str] = None


class ConsentRequest(BaseModel):
    user_id: str
    env_logging_consent: bool = True
    personalisation_consent: bool = True
    consent_version: str = "1.0"


class ConsentResponse(BaseModel):
    user_id: str
    env_logging_consent: bool
    personalisation_consent: bool
    consent_version: str
    updated_at: str


class ConsentStatusResponse(BaseModel):
    user_id: str
    env_logging_consent: bool = False
    personalisation_consent: bool = False
    consent_version: Optional[str] = None
    updated_at: Optional[str] = None
