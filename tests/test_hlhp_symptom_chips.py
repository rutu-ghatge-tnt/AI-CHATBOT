"""Symptom chip highlighting — user-selected only."""

from app.hlhp.composition.vocabulary import symptom_chips


def test_symptom_chips_default_unhighlighted():
    chips = symptom_chips("acne")
    assert len(chips) == 20
    assert all(not c["highlighted"] for c in chips)


def test_symptom_chips_highlight_only_logged_selections():
    chips = symptom_chips("acne", selected={"oily", "breakout"})
    by_kw = {c["keyword"]: c["highlighted"] for c in chips}
    assert by_kw["oily"] is True
    assert by_kw["breakout"] is True
    assert by_kw["shiny"] is False
