"""HLHP engagement API models (log, streak, weekly card, learn)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserLogRequest(BaseModel):
    user_id: str
    symptoms: list[str] = Field(min_length=1)
    areas: list[str] = Field(default_factory=list)
    local_time: datetime
    routine_action: str = "Maintain"
    rule_id: Optional[str] = None
    location_city: str = ""
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    raw_uvi: Optional[float] = Field(None, ge=0)
    raw_aqi: Optional[int] = Field(None, ge=0)
    raw_rh: Optional[float] = Field(None, ge=0, le=100)
    raw_temp: Optional[float] = None
    outdoor_ok_score: Optional[int] = Field(None, ge=0, le=100)
    mood_verdict: Optional[str] = None
    sudden_event_tags: Optional[list[str]] = None


class LoggedEventOut(BaseModel):
    ts: str
    date: str
    user_id: str
    symptoms: list[str]
    areas: list[str]
    sfi: int
    action_cluster: str
    temp_band: str
    uv_band: str
    aqi_band: str
    humidity_band: str


class UserLogResponse(BaseModel):
    logged: LoggedEventOut
    streak: int
    longest_streak: int


class StreakBadges(BaseModel):
    first_log: bool = False
    streak_7: bool = False
    streak_30: bool = False


class WeekGridDay(BaseModel):
    date: str
    done: bool
    today: bool


class StreakResponse(BaseModel):
    current_streak: int
    longest_streak: int
    badges: StreakBadges
    days_to_next_badge: int
    week_grid: list[WeekGridDay] = Field(default_factory=list)


class WeeklySeriesPoint(BaseModel):
    date: str
    sfi: Optional[int] = None


class WeeklyCardResponse(BaseModel):
    week_avg_sfi: Optional[int] = None
    trend_vs_prev: Optional[int] = None
    series: list[WeeklySeriesPoint] = Field(default_factory=list)
    logged_days: int = 0


class LearnExplainerOut(BaseModel):
    keyword: str
    title: str
    sections: list[dict]


class LearnNuggetOut(BaseModel):
    id: int
    text: str
    factor: str
    source: str = ""


class LearnSymptomChipOut(BaseModel):
    keyword: str
    highlighted: bool = False


class LearnResponse(BaseModel):
    explainers: list[LearnExplainerOut] = Field(default_factory=list)
    nuggets: list[LearnNuggetOut] = Field(default_factory=list)
    concern_id: Optional[str] = None
    city: Optional[str] = None
    symptom_keywords: list[LearnSymptomChipOut] = Field(default_factory=list)
