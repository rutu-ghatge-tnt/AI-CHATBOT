# SkinBB Unified Engine

A single, clean implementation of the Hyperlocal engine that produces seven
things from one call:

1. **Skin Friendliness Index** (0–100)
2. **Personalised SFI** — score that shifts with skin type / concern
3. **Matched Scenario** — one of 16 weather-pattern names
4. **L1 Alert** — universal action ("Don't step out without SPF 50 today.")
5. **L2 Alert** — skin-type / concern specific ("Pick a tinted sunscreen…")
6. **L3 Alert** — technique / timing ("Reapply every 90 minutes…")
7. **Science Tip** — plain-language fact + quiet citation

Single entry point. No products prescribed. No legacy fields.

## Folder layout

```
hl_engine_unified/
├── README.md                       this file
├── smoke_test.py                   runs 5 profiles through a Delhi day
└── hl_engine/
    ├── __init__.py                 exports `evaluate` and the models
    ├── models.py                   all data classes in one file
    ├── data/
    │   ├── thresholds.py           score thresholds + severity bands
    │   ├── multipliers.py          SFI personalisation (skin type / concern)
    │   ├── scenarios.py            16 scenarios × L1 + L2 dict + L3
    │   └── science_tips.py         14 plain-language facts
    └── services/
        ├── scoring.py              personalised SFI
        ├── scenario_match.py       binary classification → one of 16
        └── alert_engine.py         the single `evaluate()` entry point
```

## Public API

One function, one model.

```python
from hl_engine import evaluate, EnvironmentalData, UserProfile, SkinType, SkinConcern

env = EnvironmentalData(
    location="Delhi",
    uv_index=9.0,
    temperature_c=41.0,
    aqi=230,
    humidity_pct=22,
)

# Anonymous user (treated as normal skin, no concern)
response = evaluate(env)

# Profiled user
profile = UserProfile(
    skin_type=SkinType.OILY,
    concerns=[SkinConcern.MELASMA],
)
response = evaluate(env, profile)
```

The response carries:

```python
response.skin_friendliness_index      # 0–100
response.band                          # "Hostile Mode" / "Code Red" / …
response.band_color                    # hex string for the UI
response.is_personalized               # True if a profile shifted the score
response.factor_breakdown              # UV / temperature / AQI / humidity points
response.scenario_code                 # "HT-HA-HU-LH"
response.scenario_name                 # "Peak photopollution day"
response.alert.l1                      # universal action line
response.alert.l2                      # skin-type / concern specific line
response.alert.l3                      # technique line
response.science_tip.fact              # plain-language fact
response.science_tip.source            # citation (UI: render quietly)
```

That is the entire surface.

## How the score is personalised

Each of the four factors (UV, T, AQI, H) scores 0–25 points. The penalty
for that factor is `25 − points`. A profile multiplies the penalty by a
factor-specific number (default 1.0, capped at 1.4):

| Skin type      | UV   | T    | AQI  | H    |
|---------------|------|------|------|------|
| normal        | 1.00 | 1.00 | 1.00 | 1.00 |
| oily          | 1.00 | 1.10 | 1.20 | 1.10 |
| dry           | 1.00 | 1.10 | 1.10 | 1.30 |
| combination   | 1.00 | 1.05 | 1.10 | 1.10 |
| sensitive     | 1.20 | 1.20 | 1.30 | 1.20 |

Plus concern weights (acne, melasma, pigmentation, dehydration, redness,
aging, etc.) — see `data/multipliers.py`.

The skin-type and concern multipliers are combined per factor by
element-wise **max** — the user's most reactive axis on each factor sets
the weight.

### Example (Delhi peak summer — UVI 9 / 41 °C / AQI 230 / RH 22)

| Profile               | UV | T | AQI | H | **SFI** | Band            |
|-----------------------|----|---|-----|---|---------|-----------------|
| Anonymous / Normal    | 5  | 5 |  4  | 5 | **19**  | Hostile Mode    |
| Oily · Melasma        | 0  | 3 |  0  | 3 | **6**   | Code Red        |
| Dry · Dehydration     | 5  | 3 |  2  | 0 | **10**  | Code Red        |
| Sensitive · Redness   | 1  | 0 |  0  | 1 | **2**   | Code Red        |

Two users on the same day see meaningfully different numbers. If you want
the personalisation softer, lower the multipliers in
`data/multipliers.py` — the engine doesn't care about the numbers, just
the shape.

## How L1 / L2 / L3 work

For each scenario the data file holds three slots:

```python
1: {
    "code": "HT-HA-HU-LH",
    "name": "Peak photopollution day",

    "L1": "Don't step out without SPF 50 today.",

    "L2": {
        "default":      "Pick a broad-spectrum sunscreen.",
        "oily":         "Pick a gel or fluid (matte-finish) sunscreen.",
        "dry":          "Pick a hydrating cream-based sunscreen.",
        "sensitive":    "Pick a mineral sunscreen.",
        "melasma":      "Pick a tinted sunscreen — iron oxide also blocks visible light.",
        # …
    },

    "L3": "Reapply every 90 minutes if you're outdoors. Wash your face first.",
}
```

The engine picks L2 in this priority:

> **primary concern → skin type → "default"**

So an oily-melasma user sees the *melasma* line (concern wins).
An oily user with no concern sees the *oily* line.
An anonymous user sees the *default* line.

L1 and L3 don't change with the profile — they're either universal
("Don't step out without SPF 50") or technical ("Reapply every 90
minutes"), and those apply to everyone.

## How the Science Tip is picked

Each tip carries `tags` — `uv_high`, `aqi_high`, `humidity_low`, etc.
Each scenario carries `science_tags`. The engine picks the tip with the
greatest tag overlap. Tip selection is environmental, not profile-driven
— two users on the same day see the same fact.

## Voice rules

- **L1** — second-person imperative, no products, no skin-type assumption.
  "Don't step out without SPF 50 today."
- **L2** — "Pick / Choose / Switch to …" with the texture or filter that
  fits the user. *Why "tinted" on the melasma line:* iron-oxide tinted
  sunscreens are the only commonly-available formulas that block visible
  light. Visible light is independently melanogenic, which matters for
  melasma and PIH. (Source: Rajan, *Sunscreens for Skin of Color*, Ch. 2
  p. ~51.)
- **L3** — technique / frequency / common-mistake. Universal.
- **Science Tip** — plain-language fact. No action verbs.
- **Source** — full citation, rendered small by the UI.

## Where to edit

| You want to… | Open this file |
|---|---|
| Re-write an L1, L2 or L3 line | `data/scenarios.py` |
| Tune how strongly a skin type or concern affects SFI | `data/multipliers.py` |
| Recalibrate severity bands or thresholds | `data/thresholds.py` |
| Add / swap a science tip | `data/science_tips.py` |
| Change the binary cut for high-AQI etc. | `data/thresholds.py` (`SCENARIO_CUTS`) |

No engine code needs to change for any of these — the four service
files (`scoring.py`, `scenario_match.py`, `alert_engine.py`) are pure
mechanism.

## Smoke test

```bash
cd hl_engine_unified
python3 smoke_test.py
```

Output is documented in `README.md` above (the "Example" table).

## Pydantic

This engine uses Pydantic v2 for input/output validation. If your project
runs Pydantic v1, replace `Field(default_factory=…)` and the
`@property` lines accordingly — the rest is plain Python.
