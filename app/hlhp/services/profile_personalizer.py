from datetime import datetime

from app.hlhp.models.alert import AlertResponse
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.personalized_alert import PersonalizedAlertResponse
from app.hlhp.models.profile import UserProfile
from app.hlhp.models.score import SkinScore
from app.hlhp.services.scenario_alert_builder import build_personalized_alert_response


def personalize_alert(
    generic_alert: AlertResponse,
    profile: UserProfile,
    env: EnvironmentalData,
    score: SkinScore,
    *,
    city: str | None = None,
    local_time: datetime | None = None,
) -> PersonalizedAlertResponse:
    del generic_alert  # scenario library is the single source of alert copy
    return build_personalized_alert_response(
        env,
        score,
        profile,
        city=city,
        local_time=local_time,
    )
