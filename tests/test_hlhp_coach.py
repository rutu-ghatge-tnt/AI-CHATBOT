"""Tests for Phase 2 coach module (no LLM, no Mongo required)."""

from datetime import date, datetime, timezone

from app.hlhp.coach.assembler import assemble_coach_wrap
from app.hlhp.coach.models import ActionRecord, CoachContext, StreakRecord
from app.hlhp.coach.streak_engine import compute_streak_after_tap, current_streak, streak_key
from app.hlhp.evidence.models import EvidenceFinding


def _finding(**kwargs):
    base = {
        "id": "UV-1",
        "factor": "UV",
        "row_number": 1,
        "sub_effect": "test",
        "quantified": "",
        "mechanism": "",
        "product_implication": "",
        "outcome_tag": "",
        "confidence": "",
        "india_relevant": True,
        "source_type": "Book",
        "source_title": "T",
        "edition_year": "",
        "chapter_section": "",
        "pages_doi_pmid": "p1",
        "alert_short": "",
        "priority": "P0",
        "triggers": {
            "season": ["any"],
            "uvi": ["any"],
            "aqi": ["any"],
            "rh": ["any"],
            "temp": ["any"],
            "user_filter": [],
        },
        "alert_l1_personalised": "UV is high today.",
        "alert_l1_guest": "UV is high.",
        "never_fire": False,
        "science_citation": "Test",
        "routine_action": "apply_sunscreen",
        "mood_verdict_tag": "pigment_overdrive_day",
        "engagement_archetype": "A",
    }
    base.update(kwargs)
    return EvidenceFinding.from_dict(base)


def test_streak_survives_one_missed_day():
    key = streak_key("very_high", "apply_sunscreen")
    day1 = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    day3 = datetime(2026, 6, 3, 8, 0, tzinfo=timezone.utc)
    r1 = compute_streak_after_tap(None, streak_key_val=key, today=day1.date(), tapped_at=day1)
    r2 = compute_streak_after_tap(r1, streak_key_val=key, today=day3.date(), tapped_at=day3)
    assert r2.consecutive_days == 2


def test_streak_breaks_after_two_missed_days():
    key = streak_key("very_high", "apply_sunscreen")
    day1 = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    day4 = datetime(2026, 6, 4, 8, 0, tzinfo=timezone.utc)
    r1 = compute_streak_after_tap(None, streak_key_val=key, today=day1.date(), tapped_at=day1)
    r2 = compute_streak_after_tap(r1, streak_key_val=key, today=day4.date(), tapped_at=day4)
    assert r2.consecutive_days == 1


def test_effort_recognition_blank_for_new_user():
    ctx = CoachContext(user_id="u1", name="Priya", recent_actions=[], streaks={})
    wrap = assemble_coach_wrap(
        _finding(),
        ctx,
        uvi_band="very_high",
        day_phase="morning",
        mood_verdict="pigment_overdrive_day",
        forecast=None,
        env_uvi=8.0,
        env_aqi=120,
        local_time=datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc),
    )
    assert wrap.effort_recognition is None
    assert wrap.greeting and "Priya" in wrap.greeting


def test_effort_recognition_fires_with_action_history():
    now = datetime(2026, 6, 18, 9, 0, tzinfo=timezone.utc)
    actions = [
        ActionRecord("apply_sunscreen", now),
        ActionRecord("apply_sunscreen", now.replace(day=16)),
        ActionRecord("apply_sunscreen", now.replace(day=15)),
    ]
    ctx = CoachContext(user_id="u1", name="Priya", recent_actions=actions, streaks={})
    wrap = assemble_coach_wrap(
        _finding(),
        ctx,
        uvi_band="very_high",
        day_phase="morning",
        mood_verdict="pigment_overdrive_day",
        forecast=None,
        env_uvi=8.0,
        env_aqi=120,
        local_time=now,
    )
    assert wrap.effort_recognition is not None
