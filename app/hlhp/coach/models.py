from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Tone = Literal["gentle", "direct", "informative"]


class CoachTemplate(BaseModel):
    slot: str
    template: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    weight: int = 1
    tone: Tone = "informative"


class StreakMeta(BaseModel):
    current: int = 0
    longest: int = 0


class CoachWrap(BaseModel):
    greeting: Optional[str] = None
    continuity: Optional[str] = None
    effort_recognition: Optional[str] = None
    forward_hook: Optional[str] = None
    closer: Optional[str] = None
    action_tap_label: str = "Done ✓"
    streak_meta: Optional[StreakMeta] = None


class ActionTapRequest(BaseModel):
    user_id: str
    rule_id: Optional[str] = None
    routine_action: str
    current_time: datetime
    location_city: str
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    raw_uvi: Optional[float] = Field(None, ge=0)
    raw_aqi: Optional[int] = Field(None, ge=0)
    raw_rh: Optional[float] = Field(None, ge=0, le=100)
    raw_temp: Optional[float] = None
    outdoor_ok_score: Optional[int] = Field(None, ge=0, le=100)
    mood_verdict: Optional[str] = None
    sudden_event_tags: Optional[list[str]] = None

    @property
    def city(self) -> str:
        return self.location_city

    @property
    def local_time(self) -> datetime:
        return self.current_time


class ActionTapResponse(BaseModel):
    streak: int
    longest_ever: int
    next_check_in: str = "this evening's routine"


@dataclass
class ActionRecord:
    routine_action: str
    tapped_at: datetime
    rule_id_context: Optional[str] = None


@dataclass
class StreakRecord:
    streak_key: str
    consecutive_days: int = 0
    last_increment_at: Optional[datetime] = None
    longest_ever: int = 0


@dataclass
class CoachContext:
    user_id: str
    name: str = ""
    tone: Tone = "informative"
    recent_actions: list[ActionRecord] = field(default_factory=list)
    streaks: dict[str, StreakRecord] = field(default_factory=dict)
    suppressed_rule_ids: set[str] = field(default_factory=set)
    recent_archetypes: set[str] = field(default_factory=set)
    seen_nugget_ids: set[int] = field(default_factory=set)
    last_symptom_keyword: Optional[str] = None
    last_symptom_at: Optional[datetime] = None
