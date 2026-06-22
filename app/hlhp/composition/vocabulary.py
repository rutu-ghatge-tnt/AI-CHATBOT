"""Mood verdict → user-facing headline (UI spec §3)."""

from __future__ import annotations

_MOOD_DISPLAY = {
    "easy_day": "Today is an easy day for skin.",
    "comfortable_day": "Today is a comfortable day.",
    "manageable_day": "Today is manageable — protect the basics.",
    "combo_stress_day": "Today stacks a few stressors.",
    "stack_day": "Today stacks a few stressors.",
    "barrier_stress_day": "Today is a barrier-stress day.",
    "pigment_overdrive_day": "Today is a pigment-overdrive day.",
    "sebum_rush_day": "Today is a sebum-rush day.",
    "oxidative_load_day": "Today is an oxidative-load day.",
    "routine_day": "Today is a routine-hold day.",
    "transition_day": "Today is a transition day.",
    "transition_shock_day": "A transition is hitting your skin today.",
    "surge_day": "Today is a surge day.",
    "festival_day": "Festival rhythm is in the mix today.",
    "habit_anchor_day": "Today is a habit-anchor day.",
    "recovery_day": "Today is a recovery day.",
    "cumulative_load_day": "Today's load is building.",
}


def mood_headline(mood_tag: str) -> str:
    key = (mood_tag or "").strip().lower()
    if not key:
        return "Today is a skin-check day."
    return _MOOD_DISPLAY.get(key, f"Today is a {key.replace('_', ' ')}.")


# 20-keyword vocabulary (UI spec §5)
SYMPTOM_KEYWORDS = [
    "oily",
    "shiny",
    "breakout",
    "congested",
    "dark_spots",
    "itchy",
    "red",
    "rough",
    "sensitive",
    "tight",
    "dry",
    "flaky",
    "dull",
    "stinging",
    "tingling",
    "puffy",
    "tired_eyes",
    "tan",
    "hair_shedding",
    "scalp_itch",
]

_CONCERN_CHIP_HIGHLIGHTS: dict[str, set[str]] = {
    "acne": {"oily", "shiny", "breakout", "congested"},
    "melasma": {"dark_spots", "dull", "tan"},
    "pigmentation": {"dark_spots", "dull", "tan"},
    "pigmentation_pih": {"dark_spots", "dull", "tan"},
    "sensitivity": {"red", "stinging", "itchy", "sensitive"},
    "eczema": {"itchy", "dry", "flaky", "rough"},
    "dark_circles": {"tired_eyes", "puffy", "dull"},
    "hair_loss": {"hair_shedding", "scalp_itch"},
    "dullness": {"dull", "rough", "congested"},
}

SYMPTOM_RELATIONS: dict[str, list[str]] = {
    "oily": ["shiny", "breakout", "congested", "dark_spots"],
    "shiny": ["oily", "breakout"],
    "breakout": ["oily", "congested", "dark_spots"],
    "congested": ["oily", "breakout"],
    "dark_spots": ["tan", "dull", "breakout"],
    "itchy": ["red", "flaky", "scalp_itch"],
    "red": ["sensitive", "stinging", "itchy"],
    "rough": ["dry", "flaky", "dull"],
    "sensitive": ["red", "stinging", "tingling"],
    "tight": ["dry", "flaky", "stinging"],
    "dry": ["tight", "flaky", "rough"],
    "flaky": ["dry", "itchy", "rough"],
    "dull": ["rough", "dark_spots", "congested"],
    "stinging": ["red", "sensitive", "tight"],
    "tingling": ["sensitive", "stinging"],
    "puffy": ["tired_eyes"],
    "tired_eyes": ["puffy", "dull"],
    "tan": ["dark_spots", "dull"],
    "hair_shedding": ["scalp_itch"],
    "scalp_itch": ["hair_shedding", "itchy"],
}


def symptom_chips(
    primary_concern: str | None = None,
    *,
    selected: set[str] | frozenset[str] | None = None,
) -> list[dict]:
    """20-keyword grid — highlight only user-selected feelings (from logs), not concern defaults."""
    selected_norm = {k.strip().lower() for k in (selected or set()) if k}
    return [
        {"keyword": kw, "highlighted": kw in selected_norm}
        for kw in SYMPTOM_KEYWORDS
    ]
