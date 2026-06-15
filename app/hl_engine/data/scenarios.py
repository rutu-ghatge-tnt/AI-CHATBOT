"""
16 scenarios — each with:
    code         the 4-letter binary code
    name         the friendly scenario name
    L1           universal action statement for the day
    L2           dict keyed by skin_type / concern, with "default" as fallback
    L3           technique / timing / common-mistake guidance
    science_tags list of tags used to pick a Science Tip relevant to the day

Voice rules
-----------
L1 — conversational imperative, no product brand or texture, no skin-type
     assumption. Reads like a push notification.
L2 — "Pick / Choose / Switch to …" — the specific texture or filter that
     matches the user's skin type or concern.
L3 — "Reapply every X minutes. Wash your face first." Plain advice on the
     correct technique, applicable to everyone.
"""

# Per-scenario L2 fallback keys checked in this order:
#   user.primary_concern → user.skin_type → "default"

SCENARIOS = {

    1: {
        "code": "HT-HA-HU-LH",
        "name": "Peak photopollution day",
        "L1": "Don't step out without SPF 50 today.",
        "L2": {
            "default":      "Pick a broad-spectrum sunscreen.",
            "normal":       "Pick a broad-spectrum sunscreen.",
            "oily":         "Pick a gel or fluid (matte-finish) sunscreen.",
            "dry":          "Pick a hydrating cream-based sunscreen.",
            "combination":  "A lightweight fluid sunscreen works for both zones.",
            "sensitive":    "Pick a mineral (zinc oxide / titanium dioxide) sunscreen.",
            # concerns override skin type
            "acne":         "Pick an oil-free, non-comedogenic sunscreen.",
            "melasma":      "Pick a tinted sunscreen — iron oxide also blocks visible light.",
            "pigmentation": "Pick a tinted sunscreen — iron oxide also blocks visible light.",
            "tan":          "Pick a tinted sunscreen — visible light darkens tan too.",
            "redness":      "Pick a mineral sunscreen — chemical filters can flush sensitive skin.",
            "aging":        "Pick a broad-spectrum sunscreen and layer a vitamin C serum under it.",
        },
        "L3": "Reapply every 90 minutes if you're outdoors. Wash your face before reapplication if it's been sweaty or grimy.",
        "science_tags": ["uv_high", "aqi_high"],
    },

    2: {
        "code": "HT-LA-HU-LH",
        "name": "Hot, dry and sunny — clean air",
        "L1": "Strong sun and dry air today — sunscreen and a hat.",
        "L2": {
            "default":     "Pick a broad-spectrum sunscreen.",
            "oily":        "Pick a gel or fluid sunscreen.",
            "dry":         "Pick a hydrating cream sunscreen.",
            "combination": "A lightweight fluid sunscreen works for both zones.",
            "sensitive":   "Pick a mineral sunscreen.",
            "melasma":     "Pick a tinted sunscreen — iron oxide also blocks visible light.",
            "dehydration": "Pick a sunscreen with hyaluronic acid or glycerin in the base.",
        },
        "L3": "Reapply every 2 hours. Carry a small bottle of water — skin loses water faster in dry heat.",
        "science_tags": ["uv_high", "humidity_low"],
    },

    3: {
        "code": "HT-HA-HU-HH",
        "name": "Tropical polluted summer",
        "L1": "Sun, pollution and humidity together — wear sunscreen and cleanse well tonight.",
        "L2": {
            "default":     "Pick a fluid or gel sunscreen.",
            "oily":        "Pick an oil-free gel sunscreen.",
            "dry":         "Pick a lightweight emulsion sunscreen — humidity is doing most of the hydrating.",
            "combination": "A fluid sunscreen feels right on both zones today.",
            "sensitive":   "Pick a mineral sunscreen.",
            "acne":        "Pick an oil-free, non-comedogenic sunscreen.",
            "melasma":     "Pick a tinted sunscreen — iron oxide also blocks visible light.",
        },
        "L3": "Reapply every 90 minutes if you're outside. Rinse your face if you've been sweaty — sweat dissolves the sunscreen film.",
        "science_tags": ["uv_high", "aqi_high", "humidity_high"],
    },

    4: {
        "code": "HT-LA-HU-HH",
        "name": "Tropical sun, clean humid air",
        "L1": "Sun and sweat today — wear sunscreen and keep your routine light.",
        "L2": {
            "default":     "Pick a fluid sunscreen.",
            "oily":        "Pick an oil-free gel sunscreen.",
            "dry":         "Pick a light cream sunscreen.",
            "sensitive":   "Pick a mineral sunscreen.",
            "acne":        "Pick a non-comedogenic, oil-free sunscreen.",
            "melasma":     "Pick a tinted sunscreen.",
        },
        "L3": "Reapply every 2 hours. Don't layer heavy creams today — humid heat traps sweat under them.",
        "science_tags": ["uv_high", "humidity_high"],
    },

    5: {
        "code": "LT-HA-HU-LH",
        "name": "Winter sun in a polluted, dry city",
        "L1": "Don't be fooled by mild weather — pollution and UV are both active.",
        "L2": {
            "default":     "Pick a broad-spectrum sunscreen.",
            "oily":        "Pick a fluid sunscreen.",
            "dry":         "Pick a hydrating cream sunscreen.",
            "sensitive":   "Pick a mineral sunscreen.",
            "melasma":     "Pick a tinted sunscreen — iron oxide also blocks visible light.",
        },
        "L3": "Reapply every 2 hours outdoors. Cleanse well in the evening — fine pollution dust sticks to dry skin.",
        "science_tags": ["uv_high", "aqi_high", "humidity_low"],
    },

    6: {
        "code": "LT-LA-HU-LH",
        "name": "High-altitude winter sun",
        "L1": "Sun is stronger than it feels — wear sunscreen and lip balm.",
        "L2": {
            "default":     "Pick a broad-spectrum SPF 50.",
            "dry":         "Pick a rich cream sunscreen.",
            "sensitive":   "Pick a mineral sunscreen.",
        },
        "L3": "Reapply every 2 hours. Cover the underside of the chin and ears — snow and ice reflect UV upward.",
        "science_tags": ["uv_high", "humidity_low"],
    },

    7: {
        "code": "LT-HA-HU-HH",
        "name": "Cool, polluted, sunny and humid",
        "L1": "Pollution and sun are both active today — don't skip sunscreen.",
        "L2": {
            "default":     "Pick a fluid sunscreen.",
            "oily":        "Pick a gel sunscreen.",
            "sensitive":   "Pick a mineral sunscreen.",
        },
        "L3": "Reapply every 2 hours outdoors. Cleanse well in the evening — pollution sits on the skin all day.",
        "science_tags": ["uv_high", "aqi_high", "humidity_high"],
    },

    8: {
        "code": "LT-LA-HU-HH",
        "name": "Tropical winter — clean sun + humid",
        "L1": "Mild day — wear sunscreen anyway, UVA doesn't take days off.",
        "L2": {
            "default":     "Pick a broad-spectrum sunscreen.",
            "oily":        "Pick a gel or fluid sunscreen.",
        },
        "L3": "Reapply every 2 hours. Good day to introduce a new active if you've been planning to.",
        "science_tags": ["uv_high", "humidity_high"],
    },

    9: {
        "code": "LT-HA-LU-LH",
        "name": "Winter smog day",
        "L1": "Heavy pollution — cleanse well tonight; mild SPF in the morning.",
        "L2": {
            "default":     "Pick a moisturising sunscreen.",
            "dry":         "Pick a rich cream sunscreen with ceramides.",
            "sensitive":   "Pick a mineral sunscreen.",
            "dehydration": "Pick a sunscreen with hyaluronic acid in the base.",
        },
        "L3": "Reapply once if you're out for long. In the evening, cleanse twice — once to lift pollution, once to clean.",
        "science_tags": ["aqi_high", "humidity_low"],
    },

    10: {
        "code": "LT-LA-LU-LH",
        "name": "Mild, clean, cool dry day",
        "L1": "Easy day — keep the routine simple and don't skip morning SPF.",
        "L2": {
            "default":     "Pick a broad-spectrum sunscreen.",
            "dry":         "Pick a hydrating cream sunscreen.",
        },
        "L3": "Reapply if you're out for several hours. A good day to introduce a new active.",
        "science_tags": ["humidity_low"],
    },

    11: {
        "code": "LT-HA-LU-HH",
        "name": "Polluted coastal winter",
        "L1": "Pollution day — cleanse well in the evening.",
        "L2": {
            "default":     "Pick a fluid sunscreen.",
            "oily":        "Pick a gel sunscreen.",
            "acne":        "Pick a non-comedogenic sunscreen.",
        },
        "L3": "A salicylic-acid cleanser once or twice this week helps with monsoon breakouts.",
        "science_tags": ["aqi_high", "humidity_high"],
    },

    12: {
        "code": "LT-LA-LU-HH",
        "name": "Paradise mode — mild, clean, humid",
        "L1": "Today is easy on the skin — hold your routine.",
        "L2": {
            "default":     "Pick a light fluid sunscreen.",
        },
        "L3": "Don't skip morning SPF — visible light still gets through cloud cover.",
        "science_tags": ["humidity_high"],
    },

    13: {
        "code": "HT-HA-LU-LH",
        "name": "Hot polluted hazy dry",
        "L1": "Hot, hazy and polluted — sunscreen on, drink water.",
        "L2": {
            "default":     "Pick a fluid sunscreen.",
            "dry":         "Pick a hydrating cream sunscreen.",
            "sensitive":   "Pick a mineral sunscreen.",
        },
        "L3": "Reapply every 2 hours. Cleanse twice tonight — once for sweat, once for pollution.",
        "science_tags": ["aqi_high", "temp_high", "humidity_low"],
    },

    14: {
        "code": "HT-LA-LU-LH",
        "name": "Hot dry overcast — heat wave",
        "L1": "Heat without strong sun — moisturise twice and drink water.",
        "L2": {
            "default":     "Pick a hydrating sunscreen.",
            "dry":         "Pick a rich cream sunscreen.",
            "dehydration": "Pick a sunscreen with hyaluronic acid in the base.",
        },
        "L3": "Reapply at lunchtime. Skin still gets infrared damage from heat even when the sun is hidden.",
        "science_tags": ["temp_high", "humidity_low"],
    },

    15: {
        "code": "HT-HA-LU-HH",
        "name": "Polluted tropical monsoon",
        "L1": "Pollution + humidity day — keep your routine light and cleanse twice.",
        "L2": {
            "default":     "Pick a gel sunscreen.",
            "oily":        "Pick an oil-free gel sunscreen.",
            "acne":        "Pick a non-comedogenic gel sunscreen.",
            "melasma":     "Pick a tinted gel sunscreen — iron oxide also blocks visible light.",
        },
        "L3": "Reapply once midday. Don't sleep in makeup tonight — humid heat lets sebum and pollution oxidise on the skin overnight.",
        "science_tags": ["aqi_high", "temp_high", "humidity_high"],
    },

    16: {
        "code": "HT-LA-LU-HH",
        "name": "Clean tropical monsoon",
        "L1": "Hot and humid — wear sunscreen and keep things light.",
        "L2": {
            "default":     "Pick a fluid sunscreen.",
            "oily":        "Pick an oil-free gel sunscreen.",
        },
        "L3": "Rinse off sweat after a commute or workout — sweat residue irritates skin.",
        "science_tags": ["temp_high", "humidity_high"],
    },
}


def lookup_l2(scenario: dict, skin_type: str | None, concern: str | None) -> str:
    """Pick the L2 line that fits this user.

    Priority:  concern > skin_type > 'default' > 'normal'
    """
    l2 = scenario["L2"]
    if concern and concern in l2:
        return l2[concern]
    if skin_type and skin_type in l2:
        return l2[skin_type]
    return l2.get("default") or l2.get("normal") or ""
