"""Festival feed helpers — skin-relevant calendar only."""

from datetime import datetime

from app.hlhp.composition.feeds import (
    festival_on_date,
    nearest_skin_festival_prep,
    upcoming_skin_festivals,
)


def test_no_skin_festival_in_june():
    when = datetime(2026, 6, 18)
    assert upcoming_skin_festivals(when) == []
    assert nearest_skin_festival_prep(when) is None


def test_diwali_prep_window():
    when = datetime(2026, 10, 29)
    upcoming = upcoming_skin_festivals(when)
    assert len(upcoming) == 1
    assert upcoming[0]["id"] == "diwali"
    assert "air_quality_spike" in upcoming[0]["skin_impacts"]


def test_festival_on_diwali_day():
    fest = festival_on_date(datetime(2026, 11, 8))
    assert fest is not None
    assert fest["name"] == "Diwali"
