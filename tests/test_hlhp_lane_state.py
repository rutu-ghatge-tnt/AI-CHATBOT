"""Lane nav CTA trigger evaluation."""

from datetime import datetime

from app.hlhp.composition.lane_state import resolve_lane_states


def test_explore_default_when_no_festival_in_window():
    ctas = resolve_lane_states(when=datetime(2026, 6, 18, 12, 0, 0))
    assert ctas["explore"] == "12 guides + nuggets"


def test_explore_festival_prep_when_diwali_near():
    # Diwali 2026-11-08 — 10 days out
    ctas = resolve_lane_states(when=datetime(2026, 10, 29, 12, 0, 0))
    assert "Festival prep" in ctas["explore"]
    assert "air quality" in ctas["explore"].lower()


def test_explore_sudden_event_beats_default():
    ctas = resolve_lane_states(
        when=datetime(2026, 6, 18),
        sudden_event=True,
    )
    assert ctas["explore"] == "Monsoon onset is up next"


def test_today_barrier_stress_mood():
    ctas = resolve_lane_states(
        when=datetime(2026, 6, 18),
        mood_verdict="barrier_stress_day",
    )
    assert ctas["today"] == "Barrier-stress day"


def test_today_alert_count():
    ctas = resolve_lane_states(
        when=datetime(2026, 6, 18),
        alert_count=2,
    )
    assert ctas["today"] == "2 alerts ready"


def test_today_festival_day():
    ctas = resolve_lane_states(when=datetime(2026, 11, 8, 9, 0, 0))
    assert ctas["today"] == "Festival day today"
