from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.hlhp.services import open_meteo_uv
from app.hlhp.utils.cache import get_cached, set_cached

_CACHE_PREFIX = "hl:forecast"
_TTL = int(__import__("os").getenv("HLHP_FORECAST_CACHE_TTL", "21600"))  # 6h


@dataclass
class ForecastSnapshot:
    captured_at: datetime
    tomorrow_uvi: float | None = None
    tomorrow_aqi: int | None = None
    tomorrow_temp: float | None = None
    is_fresh: bool = False

    def eases_next_day(self, today_uvi: float, today_aqi: int) -> bool:
        if not self.is_fresh:
            return False
        if self.tomorrow_uvi is not None and self.tomorrow_uvi < today_uvi - 1:
            return True
        if self.tomorrow_aqi is not None and self.tomorrow_aqi < today_aqi - 30:
            return True
        return False


async def get_forecast(latitude: float, longitude: float) -> ForecastSnapshot:
    cache_key = f"{_CACHE_PREFIX}:{round(latitude, 2)}:{round(longitude, 2)}"
    cached = await get_cached(cache_key)
    if cached:
        return ForecastSnapshot(
            captured_at=datetime.fromisoformat(cached["captured_at"]),
            tomorrow_uvi=cached.get("tomorrow_uvi"),
            tomorrow_aqi=cached.get("tomorrow_aqi"),
            tomorrow_temp=cached.get("tomorrow_temp"),
            is_fresh=True,
        )

    try:
        by_date = await open_meteo_uv.fetch_daily_uv_max(
            latitude, longitude, days=2
        )
        # Keep temperature for coach ease check via a tiny forecast call is redundant —
        # only UV is required for eases_next_day UV branch; temp is optional context.
        dates = sorted(by_date.keys())
        tomorrow_uvi = by_date[dates[1]] if len(dates) > 1 else None
        snap = ForecastSnapshot(
            captured_at=datetime.now(timezone.utc),
            tomorrow_uvi=tomorrow_uvi,
            tomorrow_temp=None,
            is_fresh=tomorrow_uvi is not None,
        )
        await set_cached(
            cache_key,
            {
                "captured_at": snap.captured_at.isoformat(),
                "tomorrow_uvi": tomorrow_uvi,
                "tomorrow_aqi": None,
                "tomorrow_temp": None,
            },
            _TTL,
        )
        return snap
    except Exception:
        return ForecastSnapshot(captured_at=datetime.now(timezone.utc), is_fresh=False)
