"""HLHP mined pattern models — correlation between symptoms and environment."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

PatternChart = Literal["timeline", "weekgrid", "hours"]


class PatternInsight(BaseModel):
    id: str
    symptom_keyword: str
    driver: str
    title: str
    body: str
    match_pct: int = Field(ge=0, le=100)
    n: int = Field(description="Days where symptom and driver co-occurred")
    n_symptom_days: int
    baseline_pct: int = Field(ge=0, le=100, description="Driver rate across all tracked days")
    chart: PatternChart
    timeline: list[int] = Field(default_factory=list)
    weekgrid: list[int] = Field(default_factory=list, description="Symptom rate % per weekday Mon–Sun")
    hours: list[int] = Field(default_factory=list, description="Symptom log share per 2-hour bucket (12 bars)")
    cta_label: str
    cta_tag: str


class PatternsResponse(BaseModel):
    user_id: str
    days: int
    log_count: int
    min_logs_required: int = 30
    patterns: list[PatternInsight] = Field(default_factory=list)
    message: Optional[str] = None
    workbook_version: Optional[str] = None
