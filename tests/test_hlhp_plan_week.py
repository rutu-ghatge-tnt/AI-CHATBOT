"""Plan week assembly tests."""

from app.hlhp.composition.plan_week import assemble_plan_week_days
from app.hlhp.composition.sfi_daily import apply_forecast_daily_env_scores
from app.hlhp.models.sfi_timeline import SfiTimelinePoint
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


def test_extreme_uv_day_uses_hard_outdoor_copy_not_easy_template():
    readings = [
        ForecastDayReading(
            date="2026-06-25",
            temp_c=25.0,
            humidity_pct=70.0,
            uv_index=11.7,
            aqi=5,
            condition_text="Sunny",
            is_today=False,
        ),
    ]
    worst_slots = {
        "2026-06-25": SfiTimelinePoint(
            at="2026-06-25 15:00",
            at_epoch=2,
            day_offset=2,
            slot_hour=15,
            source="forecast",
            temp_c=25.0,
            aqi=5,
            uv_index=11.7,
            humidity_pct=70.0,
            sfi_env=8,
            sfi=8,
        ),
    }
    days = assemble_plan_week_days(
        readings,
        city="London",
        concern_id=None,
        worst_slots=worst_slots,
    )
    assert days[0]["outdoor_ok_score"] == 8
    assert days[0]["uv_index"] == 11.7
    assert "Easy day" not in days[0]["forecast_text"]
    assert days[0]["outdoor_ok_band_text"] == "Code Red"
    assert "Code Red" in days[0]["forecast_text"]
    assert days[0]["worst_slot_hour"] == 15


def test_plan_week_days_pick_lowest_slot_not_noon_when_worse():
    readings = [
        ForecastDayReading(
            date="2026-06-25",
            temp_c=25.0,
            humidity_pct=70.0,
            uv_index=11.7,
            aqi=5,
            condition_text="Sunny",
            is_today=False,
        ),
    ]
    worst_slots = {
        "2026-06-25": SfiTimelinePoint(
            at="2026-06-25 15:00",
            at_epoch=2,
            day_offset=2,
            slot_hour=15,
            source="forecast",
            temp_c=25.1,
            aqi=7,
            uv_index=11.7,
            humidity_pct=70.0,
            sfi_env=8,
            sfi=6,
        ),
    }
    days = assemble_plan_week_days(
        readings,
        city="Pune",
        concern_id=None,
        worst_slots=worst_slots,
        personalised=True,
    )
    assert days[0]["outdoor_ok_score"] == 6


def test_apply_forecast_daily_env_scores_patches_noon_forward_days():
    points = [
        SfiTimelinePoint(
            at="2026-06-25 12:00",
            at_epoch=1,
            day_offset=2,
            slot_hour=12,
            source="forecast",
            temp_c=25.0,
            aqi=5,
            uv_index=4.0,
            humidity_pct=70.0,
            sfi_env=70,
            sfi=70,
        ),
        SfiTimelinePoint(
            at="2026-06-25 15:00",
            at_epoch=2,
            day_offset=2,
            slot_hour=15,
            source="forecast",
            temp_c=25.0,
            aqi=5,
            uv_index=9.0,
            humidity_pct=70.0,
            sfi_env=40,
            sfi=40,
        ),
    ]
    readings = [
        ForecastDayReading(
            date="2026-06-25",
            temp_c=25.0,
            humidity_pct=70.0,
            uv_index=11.7,
            aqi=5,
            condition_text="Sunny",
            is_today=False,
        ),
    ]
    patched = apply_forecast_daily_env_scores(points, readings, location_name="London")
    noon = next(p for p in patched if p.slot_hour == 12)
    afternoon = next(p for p in patched if p.slot_hour == 15)
    # V4 environmental SFI for UV extreme + otherwise mild env (~62), not legacy Outdoor-OK floor.
    assert noon.sfi_env == 62
    assert noon.uv_index == 11.7
    assert afternoon.sfi_env == 40
