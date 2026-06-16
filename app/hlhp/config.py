import os


class HLSettings:
    WEATHER_API_URL = os.getenv(
        "HL_WEATHER_API_URL",
        "https://api.skintruth.in/api/v1/weathers/location-weather",
    )
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    WEATHER_CACHE_TTL = int(os.getenv("WEATHER_CACHE_TTL", "900"))


hl_settings = HLSettings()

