"""Tests for HLHP local calendar date keys (IST)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.hlhp.core.local_date import calendar_date_key, today_local
from app.hlhp.services.engagement_service import calendar_streak, week_grid

UTC = ZoneInfo("UTC")


def test_calendar_date_uses_ist_not_utc_slice():
    # 2026-07-01 20:30 UTC → 2026-07-02 02:00 IST
    dt = datetime(2026, 7, 1, 20, 30, tzinfo=UTC)
    assert calendar_date_key(dt) == "2026-07-02"
    assert dt.astimezone(UTC).date().isoformat() == "2026-07-01"


def test_week_grid_does_not_mark_today_done_without_log():
    today = today_local()
    dates = {(today - timedelta(days=1)).isoformat()}
    grid = week_grid(dates, today)
    today_cell = next(c for c in grid if c.today)
    assert today_cell.done is False
    assert today_cell.date == today.isoformat()


def test_week_grid_reflects_actual_log_dates_only():
    today = date(2026, 7, 1)
    dates = {"2026-06-25", "2026-06-26", "2026-06-27", "2026-06-29", "2026-06-30", "2026-07-01"}
    grid = week_grid(dates, today)
    by_date = {c.date: c.done for c in grid}
    assert by_date["2026-06-28"] is False
    assert by_date["2026-07-01"] is True


def test_calendar_streak_counts_consecutive_days_to_today():
    today = date(2026, 6, 18)
    dates = {"2026-06-16", "2026-06-17", "2026-06-18"}
    assert calendar_streak(dates, today) == 3
