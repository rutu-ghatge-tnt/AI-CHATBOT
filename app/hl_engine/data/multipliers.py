"""
SFI personalisation — penalty multipliers per skin type and concern.

How they work
-------------
1. Each factor scores 0–25 points (lower = worse day).
2. The 'penalty' for that factor is `25 - points`.
3. The penalty is multiplied by the user's multiplier (≥ 1.0).
   A sensitive user's UV penalty gets multiplied by 1.20 — so a day
   that drained 13 of the 25 UV points for a normal user drains
   15.6 points for the sensitive user.
4. The new score for that factor = max(0, 25 - new_penalty).
5. The four adjusted factor scores are summed to give the personalised
   SFI total.

Multipliers default to 1.0 (no change). For an anonymous user every
multiplier is 1.0, so the score is identical to the base environmental
score.

Where the multipliers come from
-------------------------------
Drawn from SkinBB_HLHP_Evidence_Base.xlsx — the factor each skin type or
concern is most reactive to gets the largest bump. Multipliers are
capped at 1.4 so the score never collapses on a single factor.
"""

# (factor key, default 1.0)
_FACTOR_KEYS = ("uv", "temperature", "aqi", "humidity")

# ---- Skin types ---------------------------------------------------------
SKIN_TYPE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "normal":      {"uv": 1.00, "temperature": 1.00, "aqi": 1.00, "humidity": 1.00},
    "oily":        {"uv": 1.00, "temperature": 1.10, "aqi": 1.20, "humidity": 1.10},
    "dry":         {"uv": 1.00, "temperature": 1.10, "aqi": 1.10, "humidity": 1.30},
    "combination": {"uv": 1.00, "temperature": 1.05, "aqi": 1.10, "humidity": 1.10},
    "sensitive":   {"uv": 1.20, "temperature": 1.20, "aqi": 1.30, "humidity": 1.20},
}

# ---- Concerns -----------------------------------------------------------
CONCERN_MULTIPLIERS: dict[str, dict[str, float]] = {
    "acne":         {"uv": 1.00, "temperature": 1.10, "aqi": 1.30, "humidity": 1.20},
    "melasma":      {"uv": 1.40, "temperature": 1.00, "aqi": 1.30, "humidity": 1.00},
    "pigmentation": {"uv": 1.30, "temperature": 1.00, "aqi": 1.20, "humidity": 1.00},
    "tan":          {"uv": 1.30, "temperature": 1.00, "aqi": 1.10, "humidity": 1.00},
    "aging":        {"uv": 1.30, "temperature": 1.10, "aqi": 1.20, "humidity": 1.10},
    "dullness":     {"uv": 1.10, "temperature": 1.00, "aqi": 1.30, "humidity": 1.10},
    "sensitivity":  {"uv": 1.20, "temperature": 1.20, "aqi": 1.20, "humidity": 1.10},
    "dehydration":  {"uv": 1.00, "temperature": 1.10, "aqi": 1.00, "humidity": 1.40},
    "redness":      {"uv": 1.10, "temperature": 1.30, "aqi": 1.20, "humidity": 1.00},
    "dark_circles": {"uv": 1.10, "temperature": 1.00, "aqi": 1.20, "humidity": 1.00},
    "pores":        {"uv": 1.00, "temperature": 1.10, "aqi": 1.20, "humidity": 1.10},
    "texture":      {"uv": 1.10, "temperature": 1.00, "aqi": 1.10, "humidity": 1.10},
}

NEUTRAL = {k: 1.0 for k in _FACTOR_KEYS}


def combine(skin_type: str | None, concern: str | None) -> dict[str, float]:
    """Return effective multipliers — element-wise max of the two."""
    st = SKIN_TYPE_MULTIPLIERS.get(skin_type, NEUTRAL)
    cn = CONCERN_MULTIPLIERS.get(concern, NEUTRAL) if concern else NEUTRAL
    return {k: max(st.get(k, 1.0), cn.get(k, 1.0)) for k in _FACTOR_KEYS}
