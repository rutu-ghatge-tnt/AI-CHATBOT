from __future__ import annotations

from typing import Literal, Optional, TypedDict

SkinType = Literal["oily", "combination", "normal", "dry", "very_dry"]
Texture = Literal["gel", "gel_cream", "lotion", "cream", "rich_cream", "balm", "oil", "foam", "spray", "stick", "clay", "powder"]
ContinuousPhase = Literal["aqueous", "lipidic", "silicone", "powder"]
HydrationState = Literal["hydrous", "anhydrous"]
FragranceLevel = Literal["none", "low", "standard", "heavy"]
AlcoholLevel = Literal["none", "low", "medium", "high"]
Finish = Literal["matte", "natural", "dewy", "luminous"]
Season = Literal["apr_jun", "jul_sep", "nov_feb", "mar_oct_other"]
MatrixScore = Literal["excellent", "good", "ok", "poor", "avoid"]

MATRIX_SCORE_VALUES: dict[str, int] = {"excellent": 10, "good": 7, "ok": 5, "poor": 2, "avoid": -3}


class UserFlags(TypedDict, total=False):
    sensitive_skin: bool
    eczema: bool
    rosacea: bool
    retinoid_user: bool
    post_procedure: bool
    barrier_compromised: bool
    acne_prone: bool
    fungal_acne_prone: bool
    dehydrated_oily: bool
    mature_skin: bool


class RuntimeContext(TypedDict):
    user_id: str
    skin_type: SkinType
    climate_zone: str
    season: Season
    pin_code: Optional[str]
    flags: UserFlags
    age: Optional[int]
    concerns: list[str]
    benefits: list[str]
    life_stages: list[str]


class IngredientPositionRecord(TypedDict, total=False):
    position: int
    inci_name: str
    declared_percentage: Optional[float]


class BaseFormulaRecord(TypedDict, total=False):
    texture: Texture
    is_oilfree: bool
    finish: Optional[Finish]
    hydration_state: HydrationState
    continuous_phase: ContinuousPhase
    fragrance_level: FragranceLevel
    alcohol_level: AlcoholLevel
    comedogenic_risk: Literal["low", "moderate", "high", "unknown"]
    comedogenic_drivers: list[str]
    fungal_acne_safe: Literal["yes", "caution", "no"]
    fungal_acne_triggers: list[str]
    derivation_version: str
    last_validated_at: str


class AxisScoreDetail(TypedDict):
    axis: Literal["texture", "carrier", "fragrance", "alcohol", "finish"]
    matrix_score: MatrixScore
    numeric: int
    weight: float
    contribution: float
    note: str


class BaseFormulaScore(TypedDict):
    total: float
    details: list[AxisScoreDetail]
    has_finish_axis: bool
    rationale_strings: list[str]


class OverrideApplied(TypedDict):
    family: Literal["dehydrated_oily", "acne_prone", "mature_skin", "barrier_compromised", "climate_seasonal"]
    action: Literal["promote", "demote", "escalate", "block"]
    delta: float
    reason: str
    affected_axis: Optional[str]


class OverrideResult(TypedDict):
    score_before: float
    score_after: float
    overrides_applied: list[OverrideApplied]
    blocked: bool

