# 01 — SFI Calculation (Skin Friendliness Index)

> The single most important computation in the product. This document is the
> authoritative spec for how a 0–100 SFI is produced, how it maps to a mode/band,
> how it personalises per skin-type × concern × life-stage, and how the
> time-of-day overlay works.
>
> Reference implementations:
> - Engine scoring: `reference/engine/hlhp_engine.py` (`route()`), calibration in
>   `reference/engine/backend-docs/HLHP_SFI_Calibration.md`.
> - UI scoring (used by the live demo): `reference/ui-logic/evidence.ts`
>   (`computeSFI`, `bandFor`, `dominantDriver`, `lookupCell`) and
>   `reference/ui-logic/hlhpClient.ts` (`scanFromEvidence`).
> - Band thresholds + points: sheet **"2. Bands Reference"** of the library,
>   exported into `hlhp-evidence.json → bands`.

---

## 1. Inputs

| Input | Source | Notes |
|---|---|---|
| `temperature_c` | weather feed for the user's city/GPS | °C |
| `humidity_pct` | weather feed | relative humidity % |
| `uv_index` | weather/UV feed | 0–11+ |
| `aqi` | air-quality feed | India AQI scale |
| `skin_type` | user profile | Normal / Dry / Oily / Combination / Sensitive |
| `concern` | user profile | one of 14 (Acne, Melasma, … Vitiligo) |
| `life_stage` | user profile | Male / Female / Female + Menstrual Cycle / PCOS / Pregnancy / … |
| `zone` | derived from city via `city_zone` map | HD/HH/CN/TP/CH/TN |
| `local_time` | device clock | drives the time-of-day window |

The city → zone → representative weather mapping the demo uses lives in
`hlhp-evidence.json` (`city_zone`, `zone_weather`). **In production, replace
`zone_weather` with a live weather/AQI feed for the user's actual location.**

---

## 2. The band-points model (core of the SFI)

Each of the four environmental factors is binned into a **band**, and each band
carries a **points value out of 25**. The four factors sum to a **0–100 SFI**
(4 × 25 = 100). **Higher SFI = friendlier for skin.** Optimal conditions score
the full 25; harmful extremes score 0.

### Band thresholds + points (locked — sheet "2. Bands Reference")

**Temperature**

| Band | Range | Points |
|---|---|---|
| Extreme Cold | < 5 °C | 0 |
| Cold | 5–14 °C | 5 |
| Cool | 15–19 °C | 12 |
| Optimal | 20–27 °C | 25 |
| Warm | 28–34 °C | 12 |
| Hot | 35–42 °C | 5 |
| Extreme Heat | > 42 °C | 0 |

**AQI**

| Band | Range | Points |
|---|---|---|
| Good | 0–50 | 25 |
| Satisfactory | 51–100 | 18 |
| Moderate | 101–200 | 10 |
| Poor | 201–300 | 5 |
| Very Poor | 301–400 | 2 |
| Severe | > 400 | 0 |

**UV**

| Band | Range | Points |
|---|---|---|
| Low | 0–2 | 25 |
| Moderate | 3–5 | 18 |
| High | 6–7 | 12 |
| Very High | 8–10 | 2 |
| Extreme | 11+ | 0 |

**Humidity**

| Band | Range | Points |
|---|---|---|
| Critical Low | < 10 % | 0 |
| Very Low | 10–19 % | 5 |
| Low | 20–39 % | 12 |
| Optimal | 40–60 % | 25 |
| High | 61–79 % | 12 |
| Very High | 80–89 % | 5 |
| Extreme | > 90 % | 0 |

> Note the **bell shape**: both extremes of temperature and humidity score 0;
> the comfortable middle scores 25. UV and AQI are monotonic (more = worse).

### Formula

```
band(factor, value)   = the row in Bands Reference whose Range contains value
points(factor, value) = band(factor, value).points        # 0..25
SFI = points(Temp, t) + points(UV, uv) + points(Humidity, rh) + points(AQI, aqi)
```

Reference: `computeSFI()` in `evidence.ts`:
```ts
export function computeSFI(ev, w) {
  return driverState(ev, w).reduce((s, d) => s + (d.band.points || 0), 0);
}
```

### Worked examples (verify against `hlhp-evidence.json`)

| City (zone) | Temp | AQI | UV | RH | Points (T+A+U+H) | **SFI** | Mode |
|---|---|---|---|---|---|---|---|
| Pune (TP) | 28 Warm(12) | 80 Satis(18) | 6 High(12) | 52 Optimal(25) | 12+18+12+25 | **67** | Guard Up |
| Delhi (CN) | 34 Warm(12) | 210 Poor(5) | 8 V.High(2) | 38 Low(12) | 12+5+2+12 | **31** | Hostile Mode |
| Mumbai (HH) | 32 Warm(12) | 120 Mod(10) | 7 High(12) | 82 V.High(5) | 12+10+12+5 | **39** | Battle Stations |
| Jodhpur (HD) | 40 Hot(5) | 130 Mod(10) | 10 V.High(2) | 18 V.Low(5) | 5+10+2+5 | **22** | Code Red |

---

## 3. Dominant driver

The **dominant driver** is the factor doing the most damage = the band with the
**lowest points**. It drives which scenario cell is shown, the colour coding, and
the "●" marker on the impact lines.

```
dominant = argmin over the 4 factors of points(factor, value)
```
Ties: the demo keeps array order (Temperature, UV, Humidity, AQI); production may
prefer a clinical priority (e.g. UV > AQI > Temp > Humidity — the engine uses this
tiebreaker in `hlhp_engine.py`).

---

## 4. Mode / severity band (SFI → label)

The 0–100 SFI maps to one of six **modes** (proper-noun band names — locked):

| SFI range | Mode |
|---|---|
| 85–100 | Paradise Mode |
| 70–84 | Smooth Sailing |
| 55–69 | Guard Up |
| 40–54 | Battle Stations |
| 25–39 | Hostile Mode |
| 0–24 | Code Red |

> These UI mode bands are a presentation layer. The engine's own
> `severity_band` (`hlhp_engine.py`) is the canonical source for the alert text;
> keep the two consistent. Surge conditions push the SFI down into
> Hostile/Code Red naturally via the band points (e.g. UV→Extreme = 0 pts).

---

## 5. Impact lines (per-factor Low / Medium / High)

Each factor's band points are re-expressed as a 3-level "pressure" for the Hello
screen's impact bars:

```
level(points) = "Low"    if points >= 20
              = "Medium" if points >= 10
              = "High"   otherwise     # points < 10
```
So Optimal/near-optimal = Low pressure; mid bands = Medium; harmful bands = High.
Reference: `pointsToLevel()` in `evidence.ts`.

---

## 6. Scenario-cell lookup (which evidence applies)

Given the dominant driver's band + the user's skin × concern, look up the
**Master cell** that supplies the real L0/L1/L2 alert text, risk (0–5), confidence
tier, action cluster and PMIDs.

Master cells are keyed:  `factor | band_key | skin | concern`  (all slugified).

Some concerns are covered by only a subset of factors (e.g. **Vitiligo = UV
only**, **Keloid/Dark Marks = UV + AQI**, **Fungal/Heat Rash = Humidity + Temp**).
So the lookup walks the drivers **worst-first** and returns the first that has a
cell for *this* concern + skin, then falls back:

```
1. worst→best driver: first cell at  factor|band|skin|concern         (exact)
2. worst→best driver: first cell at  factor|band|normal|concern       (any skin)
3. dominant driver:                  factor|band|skin|acne            (last resort)
```
Reference: `lookupCell()` / `lookupDriver()` in `evidence.ts`. This guarantees a
Vitiligo user on a humid day still sees a real Vitiligo (UV) cell, not an Acne
stand-in.

---

## 7. Personal SFI (concern-weighted)

The public SFI is environment-only. A **Personal SFI** reflects how *this user's
concern* reacts, using the matched cell's risk (0–5):

```
personal_sfi = clamp(0..100, SFI − cell.risk × 4)
```
(A risk-5 cell pulls the personal score 20 points below the environmental SFI.)
Reference: `scanFromEvidence()` in `hlhpClient.ts`; the engine also returns its own
`personal_sfi` (profile-weighted) — prefer the engine's in production.

---

## 8. Gender / life-stage modifier

The selected life-stage applies a **risk delta** (from sheet "13. Gender +
Life-Stage", exported to `gender_rules` keyed `state|concern`). Positive delta =
the state makes this concern worse → SFI drops:

```
rule = gender_rules[ slug(life_stage) | slug(concern) ]      # may be null
adjusted_sfi = clamp(0..100, SFI − rule.risk_delta × 4)
```
The rule also supplies a cited **"what helps" action** (shown as the tip) and an
**insight addendum** (appended to L1). Reference: `genderRule()` in `evidence.ts`,
applied in `scanFromEvidence()`.

**Worked:** Pune × Combination × Acne = SFI 67.
- life-stage *Female + Menstrual Cycle* (Acne Δ+1) → 67 − 4 = **63**
- life-stage *Female + PCOS* (Acne Δ+2) → 67 − 8 = **59**

> The `× 4` scaling (1 risk point ≈ 4 SFI points) is a UI convention chosen so a
> 0–5 risk maps onto the 0–100 SFI proportionally. Backend may calibrate this; if
> so, change it in one place and document it.

---

## 9. Time-of-day overlay (3-window model)

Scenario cells are time-blind. The **Time Overlay** sheet (exported to
`time_overlay` keyed `factor|band_key`, with `morning` / `evening` clauses) adapts
the alert to the user's **real local time**:

```
window(localHour) = "morning"  if hour < 9
                  = "daytime"  if 9 <= hour < 16
                  = "evening"  otherwise
```

| Window | Behaviour |
|---|---|
| morning (<09:00) | current conditions **+ anticipatory** clause from `time_overlay[dom].morning` (fires only when that factor's band rises later — for UV/AQI the morning clause is pre-authored to encode this; empty otherwise) |
| daytime (09:00–16:00) | the cell's **own action** unchanged (no overlay) |
| evening (≥16:00) | current conditions easing into the **repair** clause from `time_overlay[dom].evening` |

Reference: `timeWindowNow()` + `timeClause()` in `evidence.ts`. The clause is
appended to the L1 text; the active window is shown in the alert meta line.

> Production refinement (per the "Time-of-Day Logic" sheet): the anticipatory
> morning note should fire for ANY factor whose **forecast** crosses into a worse
> band later today — i.e. compare the current band to the forecast peak band. The
> demo approximates this with the pre-authored UV/AQI morning clauses; a real
> backend with an hourly forecast should implement the band-change rule directly.

---

## 10. End-to-end pseudocode (production target)

```python
def compute_today(user, weather, now):
    # 1. band points → SFI
    pts = {f: points(f, weather[f]) for f in ("Temperature","UV","Humidity","AQI")}
    sfi = sum(pts.values())                                   # 0..100

    # 2. dominant driver + scenario cell
    dom  = factor_with_lowest_points(pts)                     # clinical tiebreaker
    cell = lookup_cell(dom.band, user.skin, user.concern)     # worst-first fallback

    # 3. personalisation
    grule = gender_rules.get((user.life_stage, user.concern))
    if grule: sfi = clamp(0,100, sfi - grule.risk_delta * 4)

    # 4. time-of-day clause
    win    = time_window(now.hour)
    clause = time_overlay_clause(dom, win)                    # "" on daytime

    # 5. assemble
    mode = mode_for(sfi)
    l1   = " ".join(filter(None, [cell.l1, clause, grule and grule.addendum]))
    tip  = (grule and grule.action) or f"Action focus: {cell.action}."
    return dict(sfi=sfi, mode=mode, l0=cell.l0, l1=l1, tip=tip,
                risk=cell.risk, confidence=cell.confidence, pmids=cell.pmids,
                action_cluster=cell.action, dominant=dom.factor,
                impacts={f: level(pts[f]) for f in pts})
```
