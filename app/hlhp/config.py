import os


class HLSettings:
    WEATHER_API_URL = os.getenv(
        "HL_WEATHER_API_URL",
        "https://api.skintruth.in/api/v1/weathers/location-weather",
    )

    @property
    def WEATHERAPI_KEY(self) -> str:
        # Read live so dotenv / process env updates are picked up; strip whitespace.
        return (os.getenv("WEATHERAPI_KEY") or os.getenv("WEATHER_API_KEY") or "").strip()

    WEATHERAPI_FORECAST_URL = os.getenv(
        "WEATHERAPI_FORECAST_URL",
        "https://api.weatherapi.com/v1/forecast.json",
    )
    WEATHERAPI_HISTORY_URL = os.getenv(
        "WEATHERAPI_HISTORY_URL",
        "https://api.weatherapi.com/v1/history.json",
    )
    WEATHERAPI_CURRENT_URL = os.getenv(
        "WEATHERAPI_CURRENT_URL",
        "https://api.weatherapi.com/v1/current.json",
    )
    HL_SCENARIO_SNAPSHOT = os.getenv(
        "HL_SCENARIO_SNAPSHOT",
        "",
    )
    # Cache backend: memory | mongo | redis  (default mongo — uses existing MONGO_URI)
    CACHE_BACKEND = os.getenv("HLHP_CACHE_BACKEND", "mongo").lower()
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    WEATHER_CACHE_TTL = int(os.getenv("WEATHER_CACHE_TTL", "900"))
    FORECAST_CACHE_TTL = int(os.getenv("HLHP_FORECAST_CACHE_TTL", "21600"))
    COACH_VOICE_ENABLED = os.getenv("HLHP_COACH_VOICE_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    # Same Node API base as Label Looker — no separate Learn-only env var.
    # Property so dotenv / process env updates are picked up after import.
    @property
    def SKINBB_API_BASE_URL(self) -> str:
        return (
            os.getenv("SKIN_BB_BASE_URL")
            or os.getenv("CREDITS_API_BASE_URL")
            or os.getenv("SERVER_URL")
            or "https://api.skintruth.in"
        ).strip().rstrip("/")
    KNOWLEDGE_FEED_ENABLED = os.getenv("HLHP_KNOWLEDGE_FEED_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    KNOWLEDGE_FEED_CACHE_TTL = int(os.getenv("HLHP_KNOWLEDGE_FEED_CACHE_TTL", "3600"))
    KNOWLEDGE_FEED_FETCH_LIMIT = int(os.getenv("HLHP_KNOWLEDGE_FEED_FETCH_LIMIT", "24"))
    BLOG_FEED_ENABLED = os.getenv("HLHP_BLOG_FEED_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    BLOG_FEED_CACHE_TTL = int(os.getenv("HLHP_BLOG_FEED_CACHE_TTL", "3600"))
    BLOG_FEED_FETCH_LIMIT = int(os.getenv("HLHP_BLOG_FEED_FETCH_LIMIT", "24"))
    # In-app city-env board collector (no OS cron). Default on when weather key set.
    # HLHP_CITY_ENV_SCHEDULER=0 to disable; HLHP_CITY_ENV_POLL_SECONDS=3600 poll interval.

    # Weather quota alerts (SES email). Limits are plan ceilings you configure.
    @property
    def WEATHER_QUOTA_ALERTS_ENABLED(self) -> bool:
        return os.getenv("HLHP_WEATHER_QUOTA_ALERTS", "true").lower() not in {
            "0",
            "false",
            "no",
        }

    @property
    def WEATHERAPI_MONTHLY_LIMIT(self) -> int:
        try:
            return max(1, int(os.getenv("WEATHERAPI_MONTHLY_LIMIT", "1000000")))
        except ValueError:
            return 1_000_000

    @property
    def OPEN_METEO_DAILY_LIMIT(self) -> int:
        try:
            return max(1, int(os.getenv("OPEN_METEO_DAILY_LIMIT", "10000")))
        except ValueError:
            return 10_000

    @property
    def OPEN_METEO_MAX_CONCURRENT(self) -> int:
        """Max in-flight Open-Meteo HTTP calls per process (1 = fully serial)."""
        try:
            return max(1, int(os.getenv("HLHP_OPEN_METEO_MAX_CONCURRENT", "1")))
        except ValueError:
            return 1

    @property
    def OPEN_METEO_MIN_INTERVAL_MS(self) -> int:
        """Minimum gap between Open-Meteo requests (ms). 0 disables pacing."""
        try:
            return max(0, int(os.getenv("HLHP_OPEN_METEO_MIN_INTERVAL_MS", "200")))
        except ValueError:
            return 200


hl_settings = HLSettings()
