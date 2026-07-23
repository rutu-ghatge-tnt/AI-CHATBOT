"""HLHP history, catch-up, and consent API models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

OutdoorExposure = Literal["in", "<1", "1-3", "3+"]
LogSleep = Literal["good", "short"]
LogStress = Literal["calm", "normal", "stressed"]
LogFoodTag = Literal["home", "junk", "dairy", "spicy"]


from pydantic import BaseModel, Field


class SuddenEventEntry(BaseModel):
    date: str
    days_ago: int
    tag: str
    headline: str
    detail: str = ""


class SfiTrendPoint(BaseModel):
    date: str
    sfi: Optional[int] = None
    sudden_event: bool = False
    driver: Optional[str] = None
    feeling_logged: bool = False


class MostFiredMood(BaseModel):
    mood: str
    display: str
    days_count: int


class ReturnerBanner(BaseModel):
    show: bool = False
    days_away: int = 0
    headline: str = ""
    context: str = ""


class HistoryDayLog(BaseModel):
    date: str
    days_ago: int
    outdoor_score: Optional[int] = None
    mood_display: str
    day_description: str
    feelings: list[str] = Field(default_factory=list)
    sudden_event: bool = False
    is_sample: bool = False
    logged: bool = True


class HistoryFeelingSession(BaseModel):
    session_id: str
    committed_at: str
    date: str
    days_ago: int
    feelings: list[str] = Field(default_factory=list)
    outdoor_score: Optional[int] = None
    mood_display: str = ""
    session_description: str = ""
    sudden_event: bool = False
    driver: Optional[str] = None
    outdoor_exposure: Optional[OutdoorExposure] = None
    notes: Optional[str] = None
    areas: list[str] = Field(default_factory=list)
    sleep: Optional[LogSleep] = None
    stress: Optional[LogStress] = None
    food: list[LogFoodTag] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    user_id: str
    days: int
    scan_count: int = 0
    is_demo: bool = False
    sfi_average: Optional[float] = None
    sfi_prior_period_average: Optional[float] = None
    sfi_delta_vs_prior: Optional[float] = None
    sudden_events: list[SuddenEventEntry] = Field(default_factory=list)
    daily_logs: list[HistoryDayLog] = Field(default_factory=list)
    feeling_sessions: list[HistoryFeelingSession] = Field(
        default_factory=list,
        description="Committed feeling logs with point-in-time SFI and environment",
    )
    trend: list[SfiTrendPoint] = Field(default_factory=list)
    most_fired_mood: Optional[MostFiredMood] = None
    returner_banner: Optional[ReturnerBanner] = None
    message: Optional[str] = None
    tracking_prompt: Optional[str] = None
    show_tracking_prompt: bool = False
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
