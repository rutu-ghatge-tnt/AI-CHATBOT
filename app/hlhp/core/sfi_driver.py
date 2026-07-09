"""Map environmental readings to recap driver keys."""

from __future__ import annotations

from app.hlhp.core.bands import EnvironmentBands
from app.hlhp.models.environmental import EnvironmentalData
from app.hlhp.models.profile import UserProfile
from app.hlhp.services.sfi_unified import COMFORT_SFI_THRESHOLD, dominant_driver_key, resolve_sfi


def driver_key_for_day(
    *,
    outdoor_score_avg: float | None,
    env: EnvironmentalData,
    profile: UserProfile | None = None,
    guest_mode: bool = False,
) -> str | None:
    """Recap bar colour from the day's averaged SFI + representative env readings."""
    if outdoor_score_avg is None:
        return None
    return dominant_driver_key(
        env,
        profile,
        guest_mode=guest_mode,
        outdoor_score_avg=outdoor_score_avg,
    )


def driver_key_from_env(
    env: EnvironmentalData,
    profile: UserProfile | None = None,
    *,
    guest_mode: bool = False,
) -> str:
    return dominant_driver_key(env, profile, guest_mode=guest_mode) or "comfort"


def bands_snapshot(bands: EnvironmentBands) -> dict[str, str]:
    return {
        "temp_band": bands.temperature,
        "uv_band": bands.uvi,
        "aqi_band": bands.aqi,
        "humidity_band": bands.humidity,
    }
