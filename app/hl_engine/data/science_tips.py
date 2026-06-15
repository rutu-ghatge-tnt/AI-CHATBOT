"""
Science tips — single-sentence plain-language facts.

Voice rules
-----------
- No action verbs. ("Wear sunscreen…" → wrong)
- No jargon. ("Free radical" is fine — most readers know it.)
- Keep to one sentence where possible.
- Source = citation, rendered quietly by the UI.

Each tip carries `tags` — the alert engine picks the tip whose tags
overlap most with the day's condition tags.
"""

SCIENCE_TIPS = [
    {
        "fact": "Sun and air pollution together damage skin more than either does alone.",
        "source": "Boussouira & Pham, Skin Stress Response Pathways (Springer 2016)",
        "tags": ["uv_high", "aqi_high"],
    },
    {
        "fact": "Visible light from sun and screens causes about half of your skin's daily free-radical damage.",
        "source": "Rajan, Sunscreens for Skin of Color (Springer 2024), Ch. 2 p. 39",
        "tags": ["uv_high"],
    },
    {
        "fact": "Fair skin can burn in about 15 minutes of strong midday sun. Darker skin takes around 45 minutes — but still gets long-term damage.",
        "source": "Rajan, Sunscreens for Skin of Color (Springer 2024), Ch. 2 p. 47",
        "tags": ["uv_high"],
    },
    {
        "fact": "UVA (the wavelength that ages skin) is the same all year and passes through glass and clouds.",
        "source": "Rajan, Sunscreens for Skin of Color (Springer 2024), Ch. 2",
        "tags": ["uv_high"],
    },
    {
        "fact": "On polluted days, fine dust binds to the natural oil in your pores — that's one reason pollution worsens breakouts.",
        "source": "Draelos, Cosmetic Dermatology (Wiley 2022), Ch. 7",
        "tags": ["aqi_high"],
    },
    {
        "fact": "City pollution can strip about half of the natural vitamin E from your skin's oil layer.",
        "source": "Boussouira & Pham, Skin Stress Response Pathways (Springer 2016), Ch. 2",
        "tags": ["aqi_high"],
    },
    {
        "fact": "Below about 20% humidity, the skin's water-loss rate jumps — that's why winter rooms feel especially drying.",
        "source": "Skin Barrier (Elias & Feingold eds., CRC 2006), Ch. 11; Denda, SKINdeep 2025",
        "tags": ["humidity_low"],
    },
    {
        "fact": "Travelling from a humid place to a dry one can make skin lose water about six times faster — for the first week.",
        "source": "Skin Barrier (Elias & Feingold eds., CRC 2006), Ch. 11",
        "tags": ["humidity_low"],
    },
    {
        "fact": "Skin's barrier loses ceramides in cold dry weather — that's why a richer winter moisturiser actually helps.",
        "source": "Skin Aging Handbook (Dayan ed., 2009)",
        "tags": ["humidity_low"],
    },
    {
        "fact": "Air conditioning can dry skin nearly as much as desert air — both pull water out of the barrier.",
        "source": "Skin Barrier (Elias & Feingold eds., CRC 2006), Ch. 11",
        "tags": ["humidity_low"],
    },
    {
        "fact": "Humid heat is when dandruff yeast thrives — that's why scalp itching peaks in monsoon.",
        "source": "Skin Microbiome Handbook (Dayan ed., 2020), Ch. 7",
        "tags": ["humidity_high", "temp_high"],
    },
    {
        "fact": "Sweat dissolves the sunscreen film — even labels marked 'water-resistant' lose protection after about 80 minutes of activity.",
        "source": "Rajan, Sunscreens for Skin of Color (Springer 2024), Ch. 12",
        "tags": ["temp_high", "uv_high"],
    },
    {
        "fact": "Warmer temperatures increase sweat and oil — reapply sunscreen if you've been outdoors for a while.",
        "source": "Rajan, Sunscreens for Skin of Color (Springer 2024), Ch. 12",
        "tags": ["temp_high"],
    },
    {
        "fact": "Above about 43 °C, skin's repair system actually slows down — heat is a stressor in its own right.",
        "source": "Treatment of Dry Skin Syndrome (Lodén & Maibach 2012), Ch. 6 (Denda)",
        "tags": ["temp_high"],
    },
    {
        "fact": "A short cool-water rinse can briefly help the skin barrier recover after sun, pollution or sweat.",
        "source": "Skin Stress Response Pathways (Wondrak ed., Springer 2016), Ch. 19",
        "tags": ["temp_high", "aqi_high"],
    },
]


def pick(condition_tags: list[str]) -> dict:
    """Pick the tip whose tags best match today's actual conditions."""
    if not condition_tags:
        return SCIENCE_TIPS[0]
    tag_set = set(condition_tags)
    fully_applicable = [t for t in SCIENCE_TIPS if all(tag in tag_set for tag in t["tags"])]
    if fully_applicable:
        return min(fully_applicable, key=lambda t: len(t["tags"]))
    scored = sorted(
        SCIENCE_TIPS,
        key=lambda t: (
            sum(1 for tag in t["tags"] if tag in tag_set),
            -len(t["tags"]),
        ),
        reverse=True,
    )
    return scored[0]
