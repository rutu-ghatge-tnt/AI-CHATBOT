"""SFI timeline assembly tests."""

from datetime import date

from app.hlhp.composition.sfi_timeline import _sfi_scores
from app.hlhp.models.profile import AgeBracket, Gender, SkinConcern, SkinType, UserProfile
from app.hlhp.services.weatherapi_timeline import (
    SFI_SLOT_HOURS,
    HourlyEnvReading,
    date_window,
    extract_slot_readings,
)


def _sample_hour(date_key: str, hour: int, *, temp: float = 30.0) -> dict:
    return {
        "time_epoch": 1_700_000_000 + hour,
        "time": f"{date_key} {hour:02d}:00",
        "temp_c": temp,
        "humidity": 55,
        "uv": 4.5 if hour >= 9 and hour <= 15 else 0.2,
        "air_quality": {"pm2_5": 35.0, "us-epa-index": 2},
    }


def test_extract_slot_readings_six_slots_per_day():
    date_key = "2026-06-18"
    hours = [_sample_hour(date_key, h) for h in SFI_SLOT_HOURS]
    readings = extract_slot_readings(
        [{"date": date_key, "hour": hours}],
        source="forecast",
    )
    assert len(readings) == len(SFI_SLOT_HOURS)
    assert {r.slot_hour for r in readings} == set(SFI_SLOT_HOURS)


def test_date_window_splits_history_and_forecast():
    today, all_dates, history_dates, forecast_dates = date_window(
        tz_id="Asia/Kolkata",
        days_back=2,
        days_ahead=2,
    )
    assert isinstance(today, date)
    assert len(all_dates) == 5
    assert len(history_dates) == 2
    assert len(forecast_dates) == 3
    assert today.isoformat() in forecast_dates
    assert today.isoformat() not in history_dates


def test_sfi_scores_personalised_can_differ_from_env():
    reading = HourlyEnvReading(
        at_epoch=1,
        local_time="2026-06-18 12:00",
        date="2026-06-18",
        slot_hour=12,
        temp_c=34.0,
        humidity_pct=70.0,
        uv_index=9.0,
        aqi=140,
        source="forecast",
    )
    profile = UserProfile(
        user_id="u1",
        skin_type=SkinType.SENSITIVE,
        skin_concerns=[SkinConcern.SENSITIVITY],
        gender=Gender.FEMALE,
        age_bracket=AgeBracket.AGE_25_30,
    )
    env_sfi, personalised = _sfi_scores(reading, location_name="Pune", profile=profile)
    assert 0 <= env_sfi <= 100
    assert 0 <= personalised <= 100
    assert personalised != env_sfi
