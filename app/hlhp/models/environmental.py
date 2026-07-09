from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class LocationInput(BaseModel):
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    city: Optional[str] = None

    @model_validator(mode="after")
    def validate_input(self):
        if not self.city and (self.latitude is None or self.longitude is None):
            raise ValueError("Provide either city name or lat/lng coordinates")
        return self


class EnvironmentalData(BaseModel):
    uv_index: float = Field(..., ge=0, le=20)
    temperature_c: float = Field(..., ge=-50, le=60)
    aqi: int = Field(..., ge=0, le=500)
    humidity_pct: float = Field(..., ge=0, le=100)
    wind_kmh: float = Field(0.0, ge=0, le=200)
    wind_dir: str = ""
    gust_kmh: float = Field(0.0, ge=0, le=250)
    location_name: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_sources: dict = Field(default_factory=dict)
    raw_weather_payload: dict = Field(default_factory=dict)
    weather_api_url: str = ""

