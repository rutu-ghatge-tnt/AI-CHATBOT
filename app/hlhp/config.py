import os


class HLSettings:
    WEATHER_API_URL = os.getenv(
        "HL_WEATHER_API_URL",
        "https://api.skintruth.in/api/v1/weathers/location-weather",
    )
    WEATHERAPI_KEY = os.getenv("WEATHERAPI_KEY") or os.getenv("WEATHER_API_KEY") or ""
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
    SKINBB_API_BASE_URL = (
        os.getenv("SKINBB_API_BASE_URL")
        or os.getenv("NEXT_PUBLIC_API_URL")
        or "https://api.skintruth.in"
    ).rstrip("/")
    KNOWLEDGE_FEED_ENABLED = os.getenv("HLHP_KNOWLEDGE_FEED_ENABLED", "true").lower() not in {
        "0",
        "false",
        "no",
    }
    KNOWLEDGE_FEED_CACHE_TTL = int(os.getenv("HLHP_KNOWLEDGE_FEED_CACHE_TTL", "3600"))
    KNOWLEDGE_FEED_FETCH_LIMIT = int(os.getenv("HLHP_KNOWLEDGE_FEED_FETCH_LIMIT", "24"))


hl_settings = HLSettings()

