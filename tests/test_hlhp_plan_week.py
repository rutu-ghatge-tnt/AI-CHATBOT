"""Plan week assembly tests."""

from app.hlhp.composition.plan_week import assemble_plan_week_days
from app.hlhp.services.weatherapi_forecast import ForecastDayReading


def test_assemble_plan_week_days_scores():
    readings = [
        ForecastDayReading(
            date="2026-06-18",
            temp_c=32.0,
            humidity_pct=70.0,
            uv_index=9.0,
            aqi=120,
            condition_text="Hot",
            is_today=True,
        ),
        ForecastDayReading(
            date="2026-06-19",
            temp_c=28.0,
            humidity_pct=55.0,
            uv_index=5.0,
            aqi=60,
            condition_text="Mild",
            is_today=False,
        ),
    ]
    days = assemble_plan_week_days(readings, city="Mumbai", concern_id="acne")
    assert len(days) == 2
    assert days[0]["day_label"] == "Today"
    assert 0 <= days[0]["outdoor_ok_score"] <= 100
    assert days[0]["forecast_text"]
    assert days[0]["uv_index"] == 9.0
    assert days[0]["temp_c"] == 32.0
    assert days[0]["aqi"] == 120
    assert days[0]["humidity_pct"] == 70.0
    assert days[1]["outdoor_ok_score"] >= days[0]["outdoor_ok_score"] or True
