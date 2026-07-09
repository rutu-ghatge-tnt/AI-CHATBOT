from datetime import datetime

from app.hlhp.models.alert import AlertResponse
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.score import SkinScore
from app.hlhp.services.scenario_alert_builder import build_alert_response


def generate_alert(
    env: EnvironmentalData,
    score: SkinScore,
    *,
    city: str | None = None,
    local_time: datetime | None = None,
) -> AlertResponse:
    return build_alert_response(
        env,
        score,
        guest_mode=True,
        city=city,
        local_time=local_time,
    )
