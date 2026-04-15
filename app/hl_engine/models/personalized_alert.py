from typing import Optional

from pydantic import BaseModel

from app.hl_engine.models.alert import AlertResponse, ProtectionStep
from app.hl_engine.models.profile import SkinConcern, SkinType


class HairAlertStep(BaseModel):
    action: str
    reason: str


class HairAlert(BaseModel):
    whats_happening: str
    do_steps: list[HairAlertStep]
    key_dont: str
    hair_type_used: str
    hair_concern_used: str


class PersonalizedAlertResponse(AlertResponse):
    is_personalized: bool = True
    skin_type_used: SkinType
    primary_concern_used: SkinConcern
    fitzpatrick_type: int
    personalized_burn_time: Optional[int] = None
    personalized_steps: list[ProtectionStep]
    personalized_headline: str
    personalized_whats_happening: str
    personalized_key_dont: str
    gender_tip: Optional[str] = None
    hair_alert: Optional[HairAlert] = None
    personalized_evening_recovery: str
