from app.hl_engine.data.action_phrases import ACTION_PHRASES
from app.hl_engine.data.insight_phrases import INSIGHT_PHRASES
from app.hl_engine.models.profile import SkinConcern, SkinType


def _get_cluster(env_data) -> str:
    uv_high = env_data.uv_index >= 6
    temp_hot = env_data.temperature_c >= 30
    aqi_high = env_data.aqi > 100
    hum_high = env_data.humidity_pct >= 60
    hum_low = env_data.humidity_pct < 30

    if uv_high and temp_hot:
        return "high_uv_hot"
    if uv_high:
        return "high_uv"
    if aqi_high:
        return "high_aqi"
    if hum_high:
        return "high_humidity"
    if hum_low:
        return "low_humidity"
    return "mild"


def build_personalized_headline(concern: SkinConcern, skin_type: SkinType, env_data) -> str:
    cluster = _get_cluster(env_data)
    insight = INSIGHT_PHRASES.get((concern.value, cluster), INSIGHT_PHRASES.get((concern.value, "mild"), "Check local risk."))
    action = ACTION_PHRASES.get((skin_type.value, cluster), ACTION_PHRASES.get((skin_type.value, "mild"), "Keep routine simple."))
    return f"{insight} {action}"
