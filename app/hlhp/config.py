import os


class HLSettings:
    WEATHER_API_URL = os.getenv(
        "HL_WEATHER_API_URL",
        "https://api.skintruth.in/api/v1/weathers/location-weather",
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


hl_settings = HLSettings()

