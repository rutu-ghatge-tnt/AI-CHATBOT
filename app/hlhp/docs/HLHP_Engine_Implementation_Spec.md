# HLHP Engine — Implementation Specification
> **A portable, self-contained build specification** for SkinBB's HLHP (Hyperlocal Health
> Profile) Flash Alerts engine. Companion to the LabelLooker spec and the HLHP × LabelLooker
> Integration Blueprint.
>
> Drop this file into any project to give a reader — human or AI — the complete contract
> for what HLHP is, how it reads user state and live environment, how it scores, how it
> matches, how it composes alerts, and how it ships. §17 (Authoritative Facts) is the
> contract that wins any conflict with older artifacts.

| | |
|---|---|
| **Product surface** | HLHP — Hyperlocal Health Profile · environmental skincare alerts |
| **Status** | Spec — build-ready |
| **Parent brand** | SkinBB (Skin Beyond Borders), India |
| **Sibling specs** | LabelLooker Learnings & System Knowledge · HLHP × LabelLooker Integration Blueprint · HLHP Evidence Base (`HLHP_Evidence_Base.xlsx`, 507 cited findings) |
| **Owner** | Ajit Marathe (product, architecture) |
| **Clinical sign-off** | Dr. Soma Sarkar (safety) · Dr. Pravin Banodkar (scoring) |
| **Operating principle** | *A score informs. You decide.* |

---

## 0. How to use this document

It serves four destinations at once; read the lens that applies to you.

- **As AI context** → §17 (Authoritative Facts) is the contract.
- **For an engineer building HLHP** → §3 (profile), §5 (bands), §6 (scoring), §7 (matching), §9 (alerts) are the implementation spec.
- **For a product reviewer** → §1–§4 frame the *why*, §10 the fire budget, §12 the rollout.
- **As a general reference** → §16 (glossary) stands alone.

This document does not duplicate the LabelLooker spec or the HLHP × LL Integration Blueprint. For composition with LL2, read the Integration Blueprint. For the underlying science of every alert, read the evidence base workbook.

---

## 1. What HLHP is, and what it shows

HLHP is SkinBB's real-time environmental skincare alerts engine. It turns the user's **location, live environmental conditions, and skin profile** into a layered set of consumer-facing alerts and a per-factor 0–25 risk score.

It runs in two modes:

| Mode | Trigger | Output |
|---|---|---|
| **Guest mode** | No skin profile available | Generic, profile-free alerts driven only by location + live environment. Every alert ends with a soft profile nudge. |
| **Personalised mode** | Skin profile present (8 captured fields) | Alerts tailored to the user's concerns, type, age, gender, smoking/stress/sleep state, layered with India-first defaults. |

The evidence base behind every alert is the workbook `HLHP_Evidence_Base.xlsx` — **507 cited findings** spanning six factors (UV, Temperature, Humidity, Pollution, Nutritional Status, Lifestyle), 162 India-tagged, with structured trigger conditions, severity priorities, and category-level consumer alert text on every row.

**What HLHP is not.** Not a diagnostic tool. Not a product-recommendation engine. Not a prescription. It informs; the user decides.

---

## 2. The two user modes

### 2.1 Mode resolution

```
On every app open / refresh:
  if user has a stored profile AND profile is complete (all 8 fields):
      mode = PERSONALISED
  elif user has a partial profile:
      mode = PARTIAL_PERSONALISED  (use what's there; treat missing fields as 'any')
  else:
      mode = GUEST
```

### 2.2 Guest mode

- The engine evaluates the live environment but cannot apply any user-specific filter.
- Alerts surfaced come from the `Alert_L1_Guest` column in the evidence base.
- Every guest alert ends with a soft profile nudge — *"Build your profile to see what this means for your skin specifically."*
- The engine still prioritises India-default findings over generic global ones (see §4).
- Guest mode is **read-only** with respect to the user; the engine does not log behaviour to a profile.

### 2.3 Personalised mode

- The engine evaluates the live environment AND the user's captured profile.
- Alerts come from the `Alert_L1_Personalised` column.
- The user's profile fields (§3) are matched against each row's `Trigger_User_Filter` (§7).
- Findings whose filters require fields the user has not provided still fire if their filter is `any`; findings whose filters require a specific value the user has not supplied are suppressed.

### 2.4 Partial-personalised mode

- The bulk case in practice. User has provided some fields but not all.
- Treat missing fields as `any` — they don't constrain firing.
- The engine surfaces a one-time inline prompt suggesting the user complete the missing fields ("You'd see more specific advice if you added your sleep pattern") — gentle, dismissable, not blocking.

---

## 3. The captured profile schema

Eight fields. This is the contract. Adding fields requires sign-off; removing fields breaks existing trigger filters.

| # | Field | Vocabulary | Notes |
|---|---|---|---|
| 1 | **Age** | Integer (years) → bucketed to `18-25` / `25-40` / `40-60` / `60+` | Engine bucketises; the user enters years. |
| 2 | **Gender** | `female` / `male` / `non_binary` / `prefer_not_to_say` | Many findings are gender-conditional (melasma, hair loss, menopause); `non_binary` and `prefer_not_to_say` use the same paths as `female` for India-relevant findings unless explicitly female-only. |
| 3 | **Skin Type** | `dry` / `normal` / `combination` / `oily` / `sensitive` | Sensitivity is a modifier on a base type (per LabelLooker §5); the engine treats it as a separate filter value. |
| 4 | **Skin Concern** | Ordered list of up to 3: `acne` / `melasma` / `pigmentation` / `tan` / `aging` / `photoaging` / `eczema` / `psoriasis` / `sensitivity` / `dehydration` / `redness` / `dullness` / `dark_circles` / `large_pores` / `hair_loss` / `rosacea` | Primary concern weights heaviest; secondary and tertiary discount progressively. |
| 5 | **Skin Goal** | `prevention` / `barrier_health` / `brightening` / `anti_aging` / `acne_control` / `hydration` / `even_tone` / `general_wellness` | Aspirational; modulates which advice the engine surfaces from a tied pool. |
| 6 | **Smoking Status** | `never` / `former` / `occasional` / `regular` | Unlocks smoking-related alerts (photoaging acceleration, rosacea risk). |
| 7 | **Stress Level** | `low` / `moderate` / `high` / `very_high` | Self-reported; unlocks stress-conditional alerts (eczema flare, telogen effluvium, barrier recovery). |
| 8 | **Sleep Time** | `less_than_5h` / `5_6h` / `6_7h` / `7_9h` / `more_than_9h` | Average nightly hours; unlocks sleep-conditional alerts (barrier recovery, dark circles, aging acceleration). |

### 3.1 What the engine derives, not captures

Some user states are derived from the captured fields rather than asked directly. The engine reads the captured fields and applies these derivations on every scan:

| Derived value | Derivation rule |
|---|---|
| `mature` | `age` ≥ 45 |
| `postmenopausal` | `age` ≥ 50 AND `gender = female` |
| `dehydrated_oily` | `skin_type = oily` AND `concern includes dehydration` |
| `barrier_compromised` | `concern includes eczema OR sensitivity` OR `skin_type = sensitive` |
| `acne_prone` | `concern includes acne` OR `(skin_type = oily AND age < 30)` |
| `india_default` | All Indian users — the engine always applies this baseline regardless of other fields |

### 3.2 What HLHP does NOT capture (deliberately)

- **Medications** — not asked. Medication-conditional findings either retire to `flag:medical_advisory` (out of the firing surface) or are remapped to a concern-based filter.
- **Skin Tone (Fitzpatrick)** — not asked. India is the implicit baseline (FST IV–V). If international expansion happens, this must be added.
- **Exact location coordinates** — only city-level by default; exact GPS is opt-in for sub-city pollution variation.
- **Diet preferences** — not asked. Diet-conditional findings (vegetarian, vegan) default to `any` until/unless a diet field is added.

### 3.3 Profile completeness signals

The engine returns a `profile_completeness` score (0–8) with every personalised scan. The UI uses this to decide whether to prompt the user to add more fields — but the score itself never gates firing.

---

## 4. India-first prioritisation

HLHP's primary market is India. All defaults are India-tuned.

### 4.1 The India-default rules

1. **The implicit user is FST IV–V.** No skin-tone field is captured, so the engine assumes Indian/South Asian skin. Findings tagged `india_relevant = Y` in the workbook get a **+1 priority bonus** in the ranking layer (§10).
2. **The implicit location bucket is "Indian metro / tier-2 / coastal / hill / desert" — not global.** Seasonal definitions are the Indian calendar (§5.2).
3. **AQI bands use India's CPCB scale** (0–50 Good · 51–100 Satisfactory · 101–200 Moderate · 201–300 Poor · 301–400 Very Poor · >400 Severe). US-EPA bands are not used.
4. **Cultural anchor language** — alerts may reference monsoon, post-Diwali pollution spike, summer pre-monsoon dryness, Indian phenotypes (dehydrated-oily, brown-skin melasma, post-procedure PIH). Western framing is avoided.
5. **Sun-avoidance vs vitamin D balance** — alerts about vitamin D are India-first (Indian deficiency prevalence ~88%, slower synthesis in pigmented skin).

### 4.2 Ranking precedence (highest to lowest)

When multiple findings match the same factor + slot, the engine ranks by:

1. **Severity** — `P0` > `P1` > `P2`.
2. **India-relevance** — `india_relevant = Y` wins over `N` at equal severity.
3. **User-filter specificity** — a finding whose `Trigger_User_Filter` matches more of the user's fields wins over one with `any` (more specific = more relevant).
4. **Source quality** — corroborated > single; peer-reviewed paper > book; recent (post-2020) > older.
5. **Diversity** — once a sub-effect is surfaced, deduplicate similar sub-effects in the same slot.

---

## 5. Trigger Bands

This is the formal vocabulary the engine matches against live environmental and user state. Every band has explicit numeric breakpoints. **Adding a band or changing a breakpoint is a sign-off-gated change.**

### 5.1 Environmental bands

#### UV Index (UVI)

| Band | Range | Interpretation |
|---|---|---|
| `off` | UVI < 1 | Night / sunset / low solar elevation. **No UV-derived alert can fire in this band.** |
| `low` | 1 ≤ UVI < 3 | Minimal sunburn risk; daily routine still beneficial. |
| `moderate` | 3 ≤ UVI < 6 | Standard daytime; SPF and sun-aware behaviour matter. |
| `high` | 6 ≤ UVI < 8 | Increased risk; reapplication, shade, tinted SPF if pigmentation-prone. |
| `very_high` | 8 ≤ UVI < 11 | Extended outdoor exposure is risky; protective measures essential. |
| `extreme` | UVI ≥ 11 | Top of the scale; minimise exposure; full protection required. |

#### Temperature (ambient, °C)

| Band | Range | Interpretation |
|---|---|---|
| `very_cold` | < 10 °C | Winter dry-air territory; ceramide loss; heated indoor air worsens it. |
| `cold` | 10 ≤ T < 20 | Cold; barrier-aware routine starts here. |
| `comfortable` | 20 ≤ T < 28 | Neutral baseline. No temperature-driven concerns. |
| `warm` | 28 ≤ T < 35 | Sebum rises measurably; oily-skin concerns sharpen. |
| `hot` | 35 ≤ T < 40 | Active sweat; sunscreen photostability and reapplication intervals matter. |
| `very_hot` | ≥ 40 °C | Heat-rash risk; elderly thermoregulation concerns; aggressive sun protection. |

#### Humidity (relative humidity, %)

| Band | Range | Interpretation |
|---|---|---|
| `very_low` | RH < 30% | Severe drought conditions for skin; NMF synthesis suspended; six-fold water loss. |
| `low` | 30 ≤ RH < 50 | Dry; routine emollient strategy required. |
| `moderate` | 50 ≤ RH < 70 | Comfortable for most skin. No humidity-driven concerns. |
| `high` | 70 ≤ RH < 85 | Sebum suspension; fungal-acne risk rises; lighter textures favoured. |
| `very_high` | ≥ 85% | Sweat doesn't evaporate; Malassezia thrives; oily-prone skin needs antifungal-leaning routine. |

#### AQI (India CPCB scale)

| Band | Range | Interpretation |
|---|---|---|
| `good` | 0–50 | Clean air; no extra steps. |
| `satisfactory` | 51–100 | Routine antioxidant + cleanse adequate. |
| `moderate` | 101–200 | Pollution-aware routine becomes essential for sensitive/pigmentation-prone. |
| `poor` | 201–300 | Antioxidant layering + double-cleanse strongly recommended. |
| `very_poor` | 301–400 | Indoor-air filtration warranted; aggressive evening cleanse + repair. |
| `severe` | > 400 | Outdoor exposure should be minimised. |

#### Season (Indian calendar)

| Band | Calendar | Climate |
|---|---|---|
| `winter_dry` | Dec–Feb (North India) | Cold, low RH, dry; ceramide-loss territory. |
| `pre_monsoon` | Mar–May | Hot, rising humidity; sebum and pigment kick in. |
| `monsoon` | Jun–Sep | Hot + very high RH; fungal acne, sweat retention, lighter textures. |
| `post_monsoon` | Oct–Nov | Transitional; barrier rebuilding; pollution rises after Diwali. |
| `winter_humid` | Dec–Feb (South India, coastal) | Mild temps, moderate RH; less ceramide pressure than the North. |

### 5.2 User-state bands

#### Sleep (average nightly hours)

| Band | Range | Interpretation |
|---|---|---|
| `severely_deprived` | < 5 h | Barrier recovery is 30%+ slower; dark circles and aging acceleration strongly conditional. |
| `deprived` | 5–6 h | Barrier and dark-circles concerns moderate-to-strong. |
| `low` | 6–7 h | Sub-optimal; lifestyle alerts fire at lower priority. |
| `optimal` | 7–9 h | Baseline; sleep-conditional alerts do not fire. |
| `excess` | > 9 h | Rare; flagged for general wellness concerns, not skin. |

#### Stress (self-reported)

| Band | Self-report | Interpretation |
|---|---|---|
| `low` | "Calm, manageable" | No stress-conditional alerts fire. |
| `moderate` | "Some pressure, mostly handling it" | Stress-conditional alerts fire at P2. |
| `high` | "Frequently stressed, affecting daily life" | P1 alerts fire; eczema/psoriasis/acne flare warnings active. |
| `very_high` | "Constantly stressed, sleep / appetite / mood disturbed" | P0 alerts fire; telogen effluvium, barrier recovery, sensitivity warnings front-and-centre. |

### 5.3 The fire matching rule

A row from the evidence base fires when, simultaneously:

```
matches(Trigger_Season,   current_season)
AND matches(Trigger_UVI_Band, current_uvi_band)
AND matches(Trigger_AQI_Band, current_aqi_band)
AND matches(Trigger_RH_Band,  current_rh_band)
AND matches(Trigger_Temp_Band, current_temp_band)
AND matches(Trigger_User_Filter, user_profile)
```

Where `matches(row_value, current_value)` is:
- `True` if `row_value` is `any` or empty
- `True` if `row_value` (comma-list) contains `current_value`
- `False` otherwise

Plus two **hard preconditions** that override `any`:

1. **Night gate** — if `current_uvi_band = off`, any row whose `Alert_L1_*` mentions sunscreen / SPF / "outdoor protection" is suppressed regardless of its `Trigger_UVI_Band` value. This closes the "sunscreen alerts at midnight" class of bugs.
2. **Profile-required gate** — for `mode = GUEST`, any row whose `Trigger_User_Filter` contains a specific filter (e.g. `concern:melasma`) is suppressed. Guests only see `Trigger_User_Filter = any` findings.

---

## 6. The 0–25 per-factor scoring engine

Each factor (UV, Temperature, Humidity, Pollution) emits a 0–25 risk score based on the live band. Scores compose into a composite "outdoor-OK" score (0–100) and a severity verdict.

### 6.1 Per-factor score mapping

| Factor | Score 0–5 (Green) | 6–12 (Amber) | 13–18 (Orange) | 19–25 (Red) |
|---|---|---|---|---|
| UV | `off` / `low` | `moderate` | `high` | `very_high` / `extreme` |
| Temperature | `comfortable` | `warm` / `cold` | `hot` / `very_cold` | `very_hot` |
| Humidity | `moderate` | `high` / `low` | `very_high` / `very_low` | (n/a — rare in India) |
| Pollution (AQI) | `good` | `satisfactory` / `moderate` | `poor` | `very_poor` / `severe` |

Sleep and Stress are **not scored 0–25** — they're habit-state filters that gate specific findings.

### 6.2 The composite outdoor-OK score (0–100)

```
composite = 100 − Σ ( factor_score × factor_weight )
```

| Factor | Weight (illustrative — sign-off pending) |
|---|---|
| UV | 1.5 |
| Pollution | 1.2 |
| Temperature | 1.0 |
| Humidity | 0.6 |

Sum max with all factors at 25 = 25×1.5 + 25×1.2 + 25×1.0 + 25×0.6 = 107.5 → clip to 100. So composite ∈ [0, 100].

| Composite | Verdict | Outdoor signal |
|---|---|---|
| 80–100 | **Comfortable** | Outdoor activities are friendly to skin today |
| 60–79 | **Manageable** | Adopt one or two protective steps before going out |
| 40–59 | **Tough** | Full protective routine before outdoor exposure |
| 20–39 | **Hostile** | Minimise outdoor exposure; full protection essential if going out |
| 0–19 | **Severe** | Postpone outdoor activities; address indoor air too |

### 6.3 Per-factor band → score table (illustrative)

| Band | UV score | Temp score | RH score | AQI score |
|---|---|---|---|---|
| `off` / `comfortable` / `moderate` / `good` | 0 | 0 | 0 | 0 |
| `low` / `warm` / `cold` / `high` / `low` / `satisfactory` | 5 | 8 / 8 | 8 / 8 | 5 |
| `moderate` / `hot` / `very_cold` / `very_high` / `very_low` / `moderate` | 12 | 16 / 18 | 18 / 18 | 12 |
| `high` / `very_hot` / `poor` | 18 | 22 | — | 18 |
| `very_high` / `severe` | 22 | — | — | 22 |
| `extreme` / `very_poor` | 25 | — | — | 25 |

These values are illustrative and **flagged for clinical sign-off** before launch.

---

## 7. The trigger matching engine

This is the heart of the runtime. On every scan:

```
inputs:
  user_state = { mode, profile_fields }       # GUEST or PERSONALISED
  env_state  = { uvi, aqi, rh, temp, season, location }

resolved:
  uvi_band, aqi_band, rh_band, temp_band = bucketise(env_state)
  profile_filter_set = derive_filters(user_state)   # see §3.1
  
for each row in evidence_base:
  if night_gate_blocks(row, uvi_band): skip
  if guest_gate_blocks(row, mode): skip
  if not matches_all_trigger_bands(row, env_state, profile_filter_set): skip
  candidate_rows.append(row)

ranked = rank(candidate_rows, env_state, profile_filter_set)   # §4.2
selected = fire_budget(ranked, env_state)                       # §10
```

### 7.1 Filter-matching syntax

`Trigger_User_Filter` accepts comma-separated tokens of the form `<class>:<value>`. The supported classes are exactly the captured-schema fields plus derived states and `flag:`:

| Class | Values |
|---|---|
| `concern` | any of the 16 concerns from §3.1.4 |
| `skin_type` | `dry` / `normal` / `combination` / `oily` / `sensitive` |
| `gender` | `female` / `male` / `non_binary` |
| `age` | `18-25` / `25-40` / `40-60` / `60+` (or bucketed values like `age:45+`) |
| `smoking` | `regular` / `occasional` / `former` (never `never`) |
| `stress` | `high` / `very_high` (`low` / `moderate` don't trigger) |
| `sleep` | `severely_deprived` / `deprived` / `low` |
| `goal` | any of the 8 skin goals |
| `flag` | `medical_advisory` / `never_fire` (special markers) |

A token matches when the user's profile contains the same `(class, value)` pair, or a derived state contains it.

### 7.2 Mode resolution at the filter layer

| Mode | Filter resolution |
|---|---|
| Personalised (all 8 fields) | Match every token in `Trigger_User_Filter` against the profile. Row fires only when filter is `any` OR every token matches. |
| Partial-personalised | Tokens referring to missing fields are treated as `any` for matching (don't constrain). Other tokens evaluated as usual. |
| Guest | Only rows with `Trigger_User_Filter = any` fire. |

---

## 8. Severity ladder and composition with LL2

HLHP's severity ladder mirrors LL2's (BLOCK / HARD / SOFT / NONE) with the `_ENV` suffix:

| Severity | Trigger | Behaviour |
|---|---|---|
| `BLOCK_ENV` | All four env factors simultaneously at top-band (UVI ≥ 11 + AQI severe + RH very_low + temp very_hot) | "Postpone outdoor exposure today" banner; outdoor-OK score forced to ≤ 20. |
| `HARD_ENV` | Any single factor at `extreme` / `severe` / `very_high` / `very_low` band | Essential protective measures called out front-and-centre. |
| `SOFT_ENV` | Multiple factors at `moderate` / `high` band | Routine reminders amplified. |
| `NONE` | Comfortable composite across factors | Habit alerts only; environment-conditional alerts suppressed. |

When LL2 is composed in (per the Integration Blueprint §7):
- LL2's safety BLOCK always trumps HLHP.
- HLHP's `BLOCK_ENV` adds an outdoor-postponement notice but does not block the product score.
- Two `SOFT`s do not promote to `HARD`. Severities don't accumulate.

---

## 9. Alert layers

HLHP surfaces alerts in **three depth layers**. The workbook already carries L1; L2 and L3 are derived live or rendered from existing workbook fields.

### 9.1 Layer L1 — Lock-screen / carousel

| Variant | Column in workbook | Used when |
|---|---|---|
| `Alert_L1_Personalised` | populated, 30–50 words | mode ∈ {Personalised, Partial-personalised} |
| `Alert_L1_Guest` | populated, 30–50 words, profile-free | mode = Guest |

**Voice rules (per Glossary sheet):** plain language, no INCI / no doses / no clock-time references, category-only ingredient mentions, conditional frame per factor, strength verb scale (worth considering · recommended · highly recommended · strongly recommended · essential today).

### 9.2 Layer L2 — Tap-open explainer

Rendered live from the row's `Mechanism` + `Quantified_Value` + `Product_Implication` + a one-line bridge from the evidence behind the recommendation.

L2 may reference *specific ingredient classes by category* (still no INCI / no percentages), expanded with "why this works" — e.g. *"Antioxidant serums help because pollution oxidises facial sebum within hours; a layered antioxidant boost restores the protective film."*

L2 is generated by the Claude generation layer (per LL2 §8 — Sonnet 4.6 → Haiku 4.5 → template), with the row's structured fields as input.

### 9.3 Layer L3 — Science citation

The row's `Source: Title` + `Edition / Year` + `Chapter / Section / Journal+Author` + `Pages / DOI / PMID` — rendered as a "Source" footer. Tapping opens the DOI/PMID link (for papers) or shows the book reference.

L3 is **always available** for every fired alert. It's what makes HLHP defensible — every alert traces to a cited source.

### 9.4 Layer composition example

User: female, 32, oily skin, melasma + dark circles, high stress, 5–6h sleep.
Conditions: Mumbai monsoon evening. UVI = `off`, AQI = `moderate`, RH = `very_high`, temp = `warm`.

A row fires (Pollution, monsoon-acne + melasma intersection):

> **L1 (Personalised):** Pollution is moderate today and humidity is very high — both worsen melasma and trigger sebum-trapped breakouts. If your commute today is long, a thorough cleanse on return and a tinted mineral sunscreen for tomorrow are strongly recommended. A brightening serum at night helps pigment turnover.

> **L2 (tap-open):** PM2.5 oxidises facial sebum within hours of exposure, and high humidity prevents sweat evaporation — both compound melasma and clog pores. A category-level routine that pairs cleansing, antioxidant repair, and pigment management gives the best return for melasma-prone Indian skin during monsoon.

> **L3:** Tjiu 2025, *Life*, "Air pollution and skin aging — systematic review and meta-analysis" — DOI 10.3390/life16010061. PRISM-ISF Delphi 2025 (Kohli et al., *J Cosmet Dermatol*, PMID 40955142).

---

## 10. Fire budget and ranking

The trigger matcher can return 50–150 candidate rows on a normal day. The UI shows 3–6. The fire budget is what selects the right ones.

### 10.1 Budget per surface

| Surface | Slots | Logic |
|---|---|---|
| **Lock-screen flash card** | 1 alert (the top P0 — or top composite-verdict alert if no P0 fires) | Highest priority + India-relevant + factor with worst current band |
| **Today's main HLHP carousel** | 5 alerts | One per active factor (UV, Pollution, Temp, Humidity) plus one habit alert |
| **"Why this score" drawer** | Top 3 contributing rows per factor | Explains the composite outdoor-OK score |
| **Detailed factor view (tap on a band)** | Top 8 rows for that factor | Sorted by priority + India + user-filter specificity |
| **Daily habit drawer (Nutrition / Lifestyle)** | 3 rotated rows | Rotation key seeded by `(user_id, date)` |

### 10.2 Ranking algorithm

For each surface, candidates are ranked by:

```
score = (P0_bonus × is_P0) + (P1_bonus × is_P1) +
        (india_bonus × is_india_relevant) +
        (specificity_bonus × matched_filter_tokens) +
        (recency_bonus × is_recent) +
        (corroboration_bonus × is_corroborated)
```

Illustrative weights (sign-off pending):
- P0_bonus = 100, P1_bonus = 50, P2_bonus = 20
- india_bonus = 30
- specificity_bonus = 10 per matched non-`any` token
- recency_bonus = 5 (paper after 2020)
- corroboration_bonus = 10 (≥ 2 sources agree)

### 10.3 De-duplication

Within a surface's slot, the engine deduplicates by `sub_effect` — once one row about "PM2.5 and melasma" surfaces, similar rows are suppressed even if they'd otherwise rank well.

### 10.4 Diversity guarantee

When firing the 5-slot carousel, the engine guarantees **at most one alert per factor** in the top 5, even if 4 of the top-5 by score happen to be UV rows. This prevents "today's carousel is all sun advice" failure modes.

---

## 11. Cold-start and graceful degradation

| Missing input | Effect |
|---|---|
| No user profile (Guest) | Use `Alert_L1_Guest` everywhere; suppress rows with specific user filters. |
| No location | Fall back to "India national defaults" (national-level UVI / AQI / RH / temp medians by season). Alerts still fire on factor-agnostic findings; outdoor-OK score uses national-default bands. |
| Live env feed unavailable | Use seasonal-regional default vector `(region, month) → (median UVI, AQI, RH, temp)`. Banner notes "showing seasonal defaults — live data unavailable." |
| Profile-required field missing (partial-personalised) | Treat missing field as `any`; show a one-time soft prompt to add the field. |
| Override service unavailable | Fall back to global rules with a "degraded mode" log entry. |
| Workbook update lag | Engine reads the latest published evidence-base version (versioned snapshot, not live edits). |

All graceful-degradation paths log to `scan_logs.degraded_mode_reason` for monitoring.

---

## 12. Live-data path and workbook sync

This is the most operationally important section.

### 12.1 The data pipeline

```
HLHP_Evidence_Base.xlsx  ← (authored / reviewed by clinical sign-off)
        ↓
   (build step: validate + version + publish)
        ↓
HLHP_rules_vN.json + HLHP_alerts_vN.json + HLHP_triggers_vN.json
        ↓
   (deploy to backend rules service)
        ↓
HLHP API runtime → matches rules → returns alert payload
        ↓
Client UI renders alerts from the payload
```

### 12.2 Why a build step

The workbook is the **author surface**. The runtime needs:
- Versioned snapshots (immutable, deployable, rollbackable)
- JSON structure optimised for in-memory matching, not for Excel readability
- Validation gates (no orphan triggers, no broken citations, no INCI in L1)
- A diff view at publish time so clinical sign-off can review changes

### 12.3 Validation gates at build time

Before any new workbook version is published to the runtime:

| Gate | Rule |
|---|---|
| Citation completeness | Every row has `Source: Title` AND `Pages / DOI / PMID` |
| L1 voice rules | No INCI from the banned list, no clock-time phrases, no percentages, no FDA-without-USFDA |
| Trigger vocabulary | Every `Trigger_*` value is in the bands defined in §5 |
| User-filter schema | Every `Trigger_User_Filter` token uses a `class` from §7.1 |
| Night-gate safety | No row whose L1 mentions sunscreen has `Trigger_UVI_Band = any` only |
| Fire-budget sanity | Simulated firing at every combination of bands returns ≥1 and ≤200 rows |

A workbook that fails any gate is rejected from publication. The build prints which row failed which gate.

### 12.4 The diff review at publish time

Clinical sign-off sees a side-by-side diff:

- New rows added
- Existing rows modified (which fields changed)
- Rows removed
- Trigger condition changes
- Alert text changes

Sign-off can approve, reject, or amend before the JSON snapshot is built and deployed.

### 12.5 The live runtime contract

The runtime never reads the .xlsx directly. It reads the published JSON snapshot. The current published version is identified by a `version` field; rollback is `set published_version = vN-1`.

---

## 13. India epidemiology priorities

The findings in the evidence base that anchor India-relevant alerts are the highest-confidence rows. Engineering must NOT downrank these even when newer global research is available.

### 13.1 India-anchor sources

| Topic | Anchor |
|---|---|
| Indian sunscreen recommendations | PRISM-ISF Delphi 2025 (Kohli et al., *J Cosmet Dermatol*, PMID 40955142) |
| Melasma in Indian women | Multiple cited cohorts in workbook UV + Pollution sheets |
| Periorbital hyperpigmentation | Mendiratta 2019 (IDOJ); Ranjan 2016 (IJD) |
| Acne in Indian adolescents | Adityan 2017 (IJPD) — 72.3% prevalence in 1,032 schoolchildren |
| Indian dermatophyte / fungal acne | Kumar 2023 (Mycopathologia) — T. mentagrophytes epidemic in India |
| Indian metro pollution + skin | Singh 2024 (Dermatitis) — n = 1,510 Indian Heat Island cohort |
| Indian post-COVID telogen effluvium | Ahmad 2025 (JPMA) — 28.8% TE prevalence |
| Indian geriatric xerosis | Patel 2024 (IJCED) — 93% xerosis prevalence in South-Indian geriatric cohort |

### 13.2 Why these anchor matter

When the engine has to choose between a global-cohort finding and an Indian-cohort finding for the same intersection, the Indian finding wins — both for accuracy (Indian skin biology differs measurably) and for trust (users see references to their own context).

---

## 14. Phased rollout

| Phase | Scope | Sign-off gate |
|---|---|---|
| **1 — Guest mode MVP** | Live env feed + Alert_L1_Guest serving. No personalised mode yet. No LL2 integration. | Tile copy review by clinical sign-off. |
| **2 — Personalised mode** | Profile capture (8 fields), Alert_L1_Personalised serving, user-filter matching. | Sign-off on the 8-field schema + bucket thresholds + matching rules. |
| **3 — Trigger Bands ratification** | The bands in §5 finalised, breakpoints sign-off-locked, build-time validation gates active. | Clinical sign-off on every band's breakpoints. |
| **4 — Severity composition with LL2** | HLHP enrichment flows into LL2 per the Integration Blueprint §5–§7. | Integration Blueprint sign-offs. |
| **5 — L2 generation layer** | Claude-rendered L2 explainer cards on tap. | Generation prompt + few-shot examples + fallback ladder sign-off. |
| **6 — Composed surfaces (HLHP × LL2 deeper)** | Shelf, routine, replenishment surfaces. | Per the Integration Blueprint §14. |

### 14.1 Cut-over from current live app

The live app at `app.skintruth.in` currently surfaces alerts from an undocumented data source. Migration plan:

1. Confirm what the live runtime reads today (Engineering audit task).
2. Build the JSON snapshot from the workbook for the current band thresholds.
3. Run the new runtime in shadow mode — log what it would have served, alongside the live serving.
4. Compare for 7 days. Triage any divergence.
5. Switch live serving to the new runtime; keep the old as warm fallback for 30 days.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| **Night-gate regression** (sunscreen at UVI 0) | Build-time gate (§12.3). Live regression test that simulates UVI 0 at every city in the seed list and asserts no sunscreen alert fires. |
| **Profile-required gate slips, Guest sees personalised content** | Build-time and runtime checks. Audit logs of every guest-mode scan; periodic sample review. |
| **Band drift between workbook and live env feed** | Single source of truth for band breakpoints is §5. The env-feed integration layer must use the same bucketise function. |
| **Fire flood (>20 alerts surface at once)** | Fire budget caps per surface (§10.1). Build-time sanity test (§12.3). |
| **India-default ranking accidentally downranked** | The +30 india_bonus is a build-time constant; changes require sign-off. |
| **Alert tone drift across copy waves** | The Glossary sheet codifies voice; build-time check for INCI, clock-time phrases, FDA-without-USFDA. |
| **Engine outputs contradict each other (LL2 says Great, HLHP says BLOCK_ENV)** | Composition rules in Integration Blueprint §7 — UI absorbs both via Tile 4 amplification. |
| **Privacy compound exposure** (location + scan history) | DPDP discipline (Integration Blueprint §13). 12-month anonymisation of location and env stamps. |
| **Engine-generated L2 hallucinates a fact** | L2 is templated from structured row fields only — Claude rephrases, does not invent. Few-shot examples test this. |
| **Cold-start gives confusing reduced experience** | One-time soft onboarding prompt; explicit "showing defaults" banner when running on seasonal vectors. |

---

## 16. Glossary

| Term | Meaning |
|---|---|
| HLHP | Hyperlocal Health Profile — the environmental skincare alerts engine |
| L1 / L2 / L3 | Alert depth layers — lock-screen / tap-open explainer / source citation |
| Trigger Band | A discretisation of a continuous environmental or user-state variable into named buckets (see §5) |
| Trigger_User_Filter | Workbook column carrying comma-separated `class:value` filter tokens (§7.1) |
| Outdoor-OK score | 0–100 composite of factor risk scores (§6.2) |
| BLOCK_ENV / HARD_ENV / SOFT_ENV / NONE | HLHP's severity ladder, parallel to LL2's |
| Guest mode / Personalised mode / Partial-personalised | The three user-state regimes (§2) |
| Fire budget | The per-surface cap on how many alerts can fire (§10.1) |
| India-default | The implicit baseline — Indian / FST IV–V user — used when no skin-tone field is captured (§4) |
| Night gate | Hard rule that suppresses sunscreen alerts when UVI band is `off` (§5.3) |
| Profile-required gate | Hard rule that suppresses non-`any` filter rows in Guest mode (§5.3) |
| Live-data path | Workbook → build → JSON snapshot → runtime → API → client (§12) |

---

## 17. Authoritative facts index

*If another document — including older HLHP artifacts — contradicts these, **these win**.*

- HLHP runs in **two modes**: Guest and Personalised. Partial-personalised is a sub-case of Personalised.
- The captured profile schema is **exactly 8 fields**: Age · Gender · Skin Type · Skin Concern · Skin Goal · Smoking · Stress · Sleep. Anything beyond this is derived (§3.1).
- **Skin tone (Fitzpatrick) is not captured.** India / FST IV–V is the implicit baseline. Adding skin tone is a roadmap item for international expansion.
- **Medications are not captured.** Medication-conditional findings either retire to `flag:medical_advisory` or remap to concern-based filters.
- **AQI bands use India's CPCB scale** — not US EPA.
- **The Indian seasonal calendar** governs `Trigger_Season` — winter_dry / pre_monsoon / monsoon / post_monsoon / winter_humid.
- **Night gate is a hard precondition** — UVI band `off` suppresses every sunscreen alert regardless of `Trigger_UVI_Band` value.
- **Guest mode profile gate is a hard precondition** — non-`any` `Trigger_User_Filter` suppresses the row in Guest mode.
- **Severity ladder**: `BLOCK_ENV` / `HARD_ENV` / `SOFT_ENV` / `NONE`. Severities do not accumulate; two `SOFT`s do not become `HARD`.
- **India-relevant ranking bonus** is +30 in the rank score; changes require sign-off.
- **Fire budget**: 1 lock-screen · 5 carousel · 3 per drawer. Diversity guarantee: at most one alert per factor in the carousel.
- **Workbook is authoring; JSON snapshot is the runtime contract.** The runtime never reads the .xlsx directly.
- **Build-time validation gates are mandatory.** No published version may have orphan citations, INCI in L1, FDA without USFDA, or trigger values outside the band vocabulary.
- **L1 alert voice rules** are codified in the workbook's Glossary sheet — plain language · no INCI / doses / percentages · no clock-time references · conditional frame per factor · strength verb scale.
- **Trigger bands per §5** are the only allowed values in the trigger columns. Adding a band or changing a breakpoint is a sign-off-gated change.
- **Outdoor-OK score weighting** (UV 1.5 · Pollution 1.2 · Temperature 1.0 · Humidity 0.6) and **per-factor band → score table** are illustrative and flagged for clinical sign-off before launch.
- **L2 explainer is templated from structured workbook fields only.** Claude rephrases, never invents.
- **The live app at app.skintruth.in must be migrated** to read from the same workbook-derived JSON snapshot. Today's source is undocumented and needs an engineering audit before cut-over.

---

*A score informs. **You decide.***
*HLHP Engine — SkinBB · Implementation Spec v1*
