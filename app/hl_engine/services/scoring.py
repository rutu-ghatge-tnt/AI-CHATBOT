"""
Personalised Skin Friendliness Index.

Anonymous user → environmental SFI (the same number for everyone).
User with skin type / concern → multiplied penalties → possibly lower SFI.

Scoring is bounded:
- Each factor produces 0–25 points
- Sum is 0–100
- Severity band is picked from the 6-band table
"""

from app.hl_engine.data.multipliers import combine
from app.hl_engine.data.thresholds import (
    AQI_THRESHOLDS,
    HUMIDITY_THRESHOLDS,
    SEVERITY_BANDS,
    TEMP_THRESHOLDS,
    UV_THRESHOLDS,
    points_for,
)
from app.hl_engine.models.engine_models import EnvironmentalData, FactorBreakdown, UserProfile


def _band(total: int) -> tuple[str, str]:
    for lo, hi, name, color, *_ in SEVERITY_BANDS:
        if lo <= total <= hi:
            return name, color
    return "Code Red", "#C0392B"


def _adjust(points: int, multiplier: float) -> int:
    penalty = 25 - points
    new_penalty = penalty * multiplier
    return max(0, round(25 - new_penalty))


def compute_sfi(env: EnvironmentalData,
                profile: UserProfile | None) -> tuple[int, str, str, bool, FactorBreakdown, str]:
    """Return (sfi, band_name, band_color, is_personalized, breakdown, dominant_factor)."""

    uv_pts,   _ = points_for(env.uv_index,     UV_THRESHOLDS)
    temp_pts, _ = points_for(env.temperature_c, TEMP_THRESHOLDS)
    aqi_pts,  _ = points_for(env.aqi,           AQI_THRESHOLDS)
    hum_pts,  _ = points_for(env.humidity_pct,  HUMIDITY_THRESHOLDS)

    skin_type = profile.skin_type.value if (profile and profile.skin_type) else None
    concern   = profile.primary_concern.value if (profile and profile.primary_concern) else None

    is_personalized = bool(skin_type or concern)
    mults = combine(skin_type, concern)

    uv_adj   = _adjust(uv_pts,   mults["uv"])
    temp_adj = _adjust(temp_pts, mults["temperature"])
    aqi_adj  = _adjust(aqi_pts,  mults["aqi"])
    hum_adj  = _adjust(hum_pts,  mults["humidity"])

    total = uv_adj + temp_adj + aqi_adj + hum_adj
    band_name, band_color = _band(total)

    # Dominant factor = the one that lost the most points
    losses = {
        "uv_index":    25 - uv_adj,
        "temperature": 25 - temp_adj,
        "aqi":         25 - aqi_adj,
        "humidity":    25 - hum_adj,
    }
    dominant = max(losses, key=losses.get)

    breakdown = FactorBreakdown(uv=uv_adj, temperature=temp_adj, aqi=aqi_adj, humidity=hum_adj)

    return total, band_name, band_color, is_personalized, breakdown, dominant
