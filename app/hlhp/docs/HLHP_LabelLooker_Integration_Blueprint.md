# HLHP × LabelLooker — Integration Blueprint
> **A portable, self-contained design document.** This is the contract for how SkinBB's
> two consumer-facing intelligence engines — **HLHP** (the hyperlocal environmental
> alerts engine) and **LabelLooker** (the personalised ingredient evaluator) — share
> data and compose into one user experience.
>
> Drop this file into any project to give a reader (human or AI) full working context
> on the integration. Where it compresses content from the LabelLooker spec or the
> HLHP evidence base, it says so. §17 is the authoritative facts contract — if any
> other artifact contradicts those figures, the figures here win.

| | |
|---|---|
| **Product surface** | HLHP × LabelLooker — composed intelligence layer |
| **Status** | Spec — design-ready, not yet built |
| **Parent brand** | SkinBB (Skin Beyond Borders), India |
| **Sibling specs** | LabelLooker Learnings & System Knowledge (LL1.0 live · LL2.0 build-ready); **HLHP Engine Implementation Spec** (the canonical HLHP build contract — read for profile schema, trigger bands, scoring, fire budget); HLHP Evidence Base (`HLHP_Evidence_Base.xlsx`, **507 cited findings** across 6 factors) |
| **Owner** | Ajit Marathe (product, architecture) |
| **Clinical sign-off** | Dr. Soma Sarkar (safety rules); Dr. Pravin Banodkar (scoring rules) |
| **Shared operating principle** | *A score informs. You decide.* |
| **Doc version** | v2 — refreshed against HLHP Engine Implementation Spec v1 + post-gap-fill evidence base (507 rows) |

---

## 0. How to use this document

It serves four destinations at once; read the lens that applies to you.

- **As AI context in another Claude Project** → §17 (Authoritative Facts Index) is the
  contract: if any other document contradicts those figures, the figures here win. The
  rest is background that should not be contradicted.
- **For an engineer building either side of the integration** → §4 (architecture),
  §5 (touchpoints), §6 (scoring math), §8 (shared data model) are the implementation
  spec.
- **For a product reviewer** → §1–§3 frame the *why*, §9 shows the user surface,
  §14 is the phased rollout.
- **As a general reference** → §16 (glossary) and §17 stand alone.

This document **does not duplicate** the LabelLooker spec or the HLHP evidence base.
Treat it as the bridge — what each engine gives the other, how they compose, what
gets shared. For internal LL2 mechanics, read the LabelLooker doc. For the underlying
HLHP science, read the workbook.

---

## 1. What the integration is — and isn't

**Is.** A composition layer where LL2's *who-you-are × what's-in-the-product* analysis
is enriched by HLHP's *where-you-are × what-today-is* signal, surfaced as additional
intelligence inside both products' user surfaces.

**Is not.** A merger of the two engines. A new third product. A replacement for either
existing surface. A "buy this because the weather says so" recommendation system.

**One-line positioning.** *Two engines, one understanding of the user's moment.*

The integration exists because each engine, alone, has a blind spot the other fills:

| Engine | Knows | Blind to |
|---|---|---|
| LabelLooker (LL2.0) | User skin profile · product INCI · PRAC metadata · safety/suitability/observational rules | Today's weather · pollution · season · location |
| HLHP | Live UV / AQI / PM2.5 / RH / temperature · location · season · user skin profile · 345 cited dermatology findings | What the user owns · what they're about to buy · what's inside the bottle |

Together they answer questions neither can answer alone — most importantly,
*"is this product right for me, right now?"* and *"given today's air, what from my
shelf should I actually use?"*

---

## 2. The two engines summarised

This section compresses the two sibling specs to the minimum needed for integration
work. Read the source documents for depth.

### LabelLooker 2.0

Personalised skincare ingredient evaluator. **Three deterministic engines** — Safety,
Suitability, Observational — feed a structured result that **Claude renders into
prose** for a 5-tile carousel (Score · What works · Falls short · Worth knowing ·
Unmet needs). Engines decide; the model never decides. Score 0–100, banded into
Great / Good / Low / Gate. Type match imposes a hard ceiling
(`final_score = min(raw, ceiling)`). India-first overrides for phenotype, season,
sensitivity. Live LL1.0 since Oct 2024; LL2.0 spec complete, build-ready.

### HLHP

Hyperlocal environmental skincare alerts engine. **Six factors**: UV/UVI, Temperature,
Humidity, Pollution/AQI, Nutritional Status, Lifestyle. Per-factor 0–25 score with
behaviour-conditional consumer alerts; **507 cited findings** from dermatology textbooks
and 2015–2026 peer-reviewed literature. India-tagged throughout (≈300 of 507 rows after
the gap-fill waves). Status: evidence base assembled and trigger metadata complete; engine
specification documented in the **HLHP Engine Implementation Spec** — read it for the
8-field profile schema, the formal Trigger Bands (UVI / Temp / RH / AQI / Season / Sleep
/ Stress), the per-factor scoring, the night gate, and the fire budget. This Integration
Blueprint covers only how HLHP composes with LL2.

### What they already share

- **The *"a score informs, you decide"* operating principle.**
- **India-first product philosophy.**
- **Conservatism by design** — clinical sign-off gates any new rule.
- **DPDP-compliant data posture** (consent · phone hashing · progressive anonymisation after 2 years inactivity).
- **Brand-voice and authoritative-fact discipline** — USFDA (not FDA); no Indian-label active percentages in consumer copy; fatty alcohols are emollients; no fabricated narratives.

**Note on the user profile.** HLHP's captured profile is **8 fields** (Age · Gender · Skin Type · Skin Concern · Skin Goal · Smoking · Stress · Sleep), per the Implementation Spec §3. LL2's profile is broader (allergies, conditions, medications, life stage, fungal-acne flag). The two engines share a *common subset* and each has fields the other doesn't. The Integration's Shared Data Model (§8) covers both.

---

## 3. Integration philosophy

Four commitments, non-negotiable. They govern every design choice in §4 through §15.

1. **Score informs, you decide — composed.** No surface in the integration may
   shift toward purchase or away from another product. Composition can say *"this
   matches today's conditions"*; it cannot say *"buy this."* Same principle, applied
   across two engines.
2. **Engines remain independently auditable.** Composition happens at the orchestrator
   layer, not by mixing internals. Either engine can be re-run, replayed, or rolled
   back without the other being aware.
3. **India overrides live in one shared layer.** LL2 has phenotype/season/sensitivity
   overrides. HLHP has region/season/climate overrides. They must not double-count.
   A single override service serves both engines.
4. **Composition must not slow the decision.** LL2's user-perceived latency is already
   2–4s, dominated by Claude tile generation. Adding HLHP must be parallelised so the
   user-perceived budget stays the same. Hard rule: integration cannot add more than
   300ms p95 to LL2's existing latency.

---

## 4. System architecture — composed flow

The composed scan retains LL2's existing 10-step flow as the spine. HLHP touches it
in three places: a parallel environmental fetch (step 4½), an environmental input to
the suitability engine (step 6), and an environmental-context contribution to Tile 4
(step 9).

```
LL2 baseline flow                          HLHP integration points
─────────────────                          ───────────────────────
1. Trigger (badge tap)
2. Identity (WhatsApp OTP / session)
3. Profile load
4. Request shaped                    ┐
                                     ├──► 4½. HLHP env fetch
                                     │      (parallel, ≤200ms)
5. Safety engine                     │
6. Suitability engine ◄──────────────┘  ──► env context object
   (with env-aware ceiling)                  consumed as input
7. Ceiling & band
8. Observational overlay  ◄────────────────► env-driven observations
                                              merged with LL2's library
9. Prose generation
   (Claude renders all 5 tiles      ◄────── env context appears in
    from structured result)                  Tile 4 "Worth knowing today"
10. Render + log + feedback
    (scan log env-stamped)
```

Two architectural calls anchor this:

- **HLHP is read by LL2, not the other way around.** Inside a LabelLooker scan, HLHP
  is a synchronous *enrichment service* — fast, cacheable, optional. LL2 does not
  call back into HLHP during the same request.
- **Reverse direction is asynchronous.** When HLHP surfaces alerts ("PM2.5 high
  today"), it can recommend products from the user's LL2 scan history — but those
  lookups happen in HLHP's own UI request, not inside an LL2 scan.

This keeps the dependency one-directional during the critical scan path, and avoids
synchronous circular calls.

---

## 5. Integration touchpoints

Five concrete touchpoints. Each has an owner, a contract, and a failure mode.

### Touchpoint A — HLHP → LL2 input enrichment

**Direction.** HLHP → LL2 (synchronous, inside the scan path)

**What flows.** An `EnvironmentContext` object (schema in §8). UVI band, AQI band,
RH band, temp band, season tag, region tag, derived "environmental stress"
composite.

**Contract.** LL2's orchestrator accepts this object as an additional input alongside
profile + product. It is **optional** — if absent or stale, LL2 runs as today.

**Failure mode.** HLHP feed unavailable → LL2 proceeds without env context. Logged.
Tile 4 omits the env-conditional line.

### Touchpoint B — LL2 → HLHP product context

**Direction.** LL2 → HLHP (asynchronous, in HLHP's own surfaces)

**What flows.** The user's LL2 scan history with timestamps, band, key actives,
vehicle type, comedogenic risk, fungal-acne-safe flag. Per-product summary, not the
full carousel.

**Contract.** HLHP queries this when it wants to personalise an alert (e.g.
*"From your shelf, X is your best match today"*).

**Failure mode.** LL2 history unavailable → HLHP shows generic product-type
recommendations (e.g. *"a 10–15% vitamin-C serum is recommended"*).

### Touchpoint C — Shared override layer

**Direction.** Both engines read.

**What flows.** India phenotype overrides (dehydrated-oily, mature, barrier-compromised,
acne-prone, sensitive), seasonal overrides (Apr–Jun, Jul–Sep, Nov–Feb), climate-region
overrides (metro pollution, monsoon humidity, dry winter, hill stations).

**Contract.** Single source of truth, versioned, owned by clinical sign-off. Both
engines call it; neither maintains its own copy. (See §10.)

**Failure mode.** Override service unavailable → both engines fall back to global
defaults, with a "degraded mode" log entry.

### Touchpoint D — Shared scan log

**Direction.** Both write.

**What flows.** Every LL2 scan is stamped with the env snapshot in force at scan time.
Every HLHP alert delivery is stamped with the user profile context (in summary form).
One unified log table.

**Contract.** Append-only, env-stamped, retained indefinitely under DPDP discipline
(§13). Used for analytics, A/B, personalisation, and feedback loops.

**Failure mode.** Log write failure does not block the user response. Buffered and
retried.

### Touchpoint E — Cross-engine alerts

**Direction.** HLHP → LL2 lookup (asynchronous).

**What flows.** When an HLHP alert recommends a product type (vitamin-C serum,
ceramide cream, tinted SPF), the alert surface can call LL2 for *"best match from
this user's history"*. The lookup uses the user's existing LL2 scores; it does not
trigger a fresh scoring run.

**Contract.** Read-only. No new scan. No purchase prompt — the alert references the
product by name, the user decides.

**Failure mode.** Lookup unavailable → generic product-type recommendation.

---

## 6. Environment-aware scoring math

The hardest design decision. Two principles guard against the easy mistakes.

### Principle 1 — Environment modulates, does not override

LL2's existing suitability math (Concerns 55% · Type ceiling · Benefits) stays intact.
Environment enters as a **second ceiling**:

```
final_score = min(raw_score, type_ceiling, environmental_ceiling)
```

Most days, `environmental_ceiling = 100` and nothing changes. On adverse days, the
environmental ceiling tightens. Mechanism, not magnitude.

### Principle 2 — Environmental ceilings only tighten; they never lift

If type ceiling already caps the score at 55 (oily user × dry-skin product), env
ceiling cannot raise it to 70. Suitability remains the priority gate. Environment can
make a Great match into a Good match; it cannot promote a Low match.

### Worked examples

| Product | User | Environment | Type ceiling | Env ceiling | Final |
|---|---|---|---|---|---|
| Rich ceramide cream | Dry skin, dehydrated | Delhi winter (RH 25%, 5°C) | 100 | 100 | unchanged — perfect day for this product |
| Same rich ceramide cream | Oily skin | Mumbai monsoon (RH 85%, 32°C) | 55 (OPP) | 50 | falls further — even worse fit today |
| Heavy occlusive balm | Oily-acne | Same Mumbai monsoon | 55 (OPP) | 45 | low + flagged for fungal-acne caution today |
| Broad-spectrum SPF 30 PA+++ tinted iron-oxide | FST IV, melasma | Delhi noon, UVI 11 | 100 | 100 | Tile 4 amplifies — "essential today" |
| Vitamin-C 15% + ferulic serum | Combination, photoaging concern | Delhi PM2.5 80, UVI 8 | 80 (ADJ) | 80 | unchanged — antioxidants more valuable today |

### Environmental ceiling table (illustrative — subject to clinical sign-off)

| Factor band | Effect on score |
|---|---|
| UVI extreme (≥11) × product with photoreactive actives (retinoid in AM use, AHA top-5) | Env ceiling 70; observational adds *"AM use risky today"* |
| AQI very poor (PM2.5 >150) × product without antioxidant content | Env ceiling 80; observational adds *"layer an antioxidant serum today"* |
| Humidity very low (<30% RH) × product high in denatured alcohol (top-5 INCI) | Env ceiling 60; observational adds *"can worsen tightness today"* |
| Humidity very high (>80% RH) × heavy occlusive vehicle × oily/acne-prone | Env ceiling 50; observational adds *"may trap sweat today"* |
| Temperature very high (>35°C) × sunscreen with low photostability flag | Env ceiling 75; observational adds *"reapply more often today"* |
| All factors normal | Env ceiling 100 (no effect) |

These thresholds are **flagged for stakeholder sign-off** alongside LL2's band
cutoffs. They map directly onto the HLHP evidence base — every threshold is anchored
to a cited finding in the workbook.

### Concern weight modulation (Phase 3, deferred)

In a later phase, environment can also nudge LL2's 33/14/8 concern weights — e.g. if
the user's primary concern is *barrier sensitivity* and humidity is very low, primary
concern can lift to 38, secondary drops to 11. **Phase 3 only**; v1 keeps weights
fixed and uses only the env ceiling.

---

## 7. Severity ladder composition

LL2 has a four-level safety severity ladder: `BLOCK` / `HARD` / `SOFT` / `NONE`. HLHP
needs a parallel ladder for environmental severity. They compose by the
*highest-severity-wins* rule, with clear UI behaviours when they disagree.

### LL2 ladder (existing)

| Severity | LL2 behaviour |
|---|---|
| `BLOCK` | Short-circuit; no score; safer-options view |
| `HARD` | Score withheld unless user overrides |
| `SOFT` | Continue scoring; flag for Tile 4 |
| `NONE` | Continue normally |

### HLHP ladder (new, mirrors LL2)

| Severity | HLHP behaviour | Example trigger |
|---|---|---|
| `BLOCK_ENV` | Override the outdoor-OK signal entirely | UVI ≥12 + AQI ≥350 simultaneously |
| `HARD_ENV` | Essential protective measures required before exposure | UVI ≥11 OR AQI ≥300 |
| `SOFT_ENV` | Recommended caution; tile copy amplifies | UVI 8–10, AQI 150–300, RH <30, temp >35 |
| `NONE` | Normal day; alerts run as usual | Comfortable conditions |

### Composition rules

1. **Safety always trumps suitability.** An LL2 `BLOCK` (e.g. pregnancy × retinoid)
   short-circuits regardless of HLHP. The product score isn't shown, env or no env.
2. **HLHP `BLOCK_ENV` adds an outdoor-postponement notice but does not block the
   product score.** The product may still be a Great match; the verdict reads
   *"Great match for you — consider postponing outdoor use today."*
3. **The highest-severity verdict drives the tile tone, not the score.** An LL2
   `SOFT` + HLHP `HARD_ENV` produces a calm-but-firm Tile 4. An LL2 `HARD` + HLHP
   `NONE` keeps LL2's override flow with no env mention.
4. **Two `SOFT`s do not promote to `HARD`.** Severity does not arithmetically
   accumulate. This protects against alert fatigue.

---

## 8. Shared data model

The integration's data contract. Schemas are sketched here in the same style as the
LabelLooker spec; production-grade Pydantic/SQLAlchemy definitions live in code.

### `UserProfile` (canonical, shared)

```
user_id            : UUID
skin_type          : enum (dry / normal / combination / oily / sensitive*)
                     * sensitivity is a modifier on a base type, not a base type
concerns           : ordered list[primary, secondary, tertiary]
                     (e.g. ["melasma", "barrier", "tan"])
allergies          : list[INCI strings]
conditions         : list[rosacea, eczema, psoriasis, atopic, ...]
medications        : list[isotretinoin, topical retinoid, hydroquinone, ...]
age                : int
fitzpatrick_type   : enum (I, II, III, IV, V, VI)
life_stage         : enum (none / pregnancy / nursing / minor)
fungal_acne_flag   : bool (user self-flag for Malassezia folliculitis)
sensitivity_flags  : list[fragrance / alcohol / essential oils / ...]
created_at, updated_at
```

### `EnvironmentContext` (HLHP → LL2)

```
location           : { region: str, city: str, lat?: float, lng?: float }
captured_at        : timestamp
uvi                : { value: float, band: enum(low|moderate|high|very_high|extreme) }
aqi                : { value: int, pm25: float, band: enum(good|moderate|poor|very_poor|severe) }
humidity_rh        : { value: float, band: enum(very_low|low|moderate|high|very_high) }
temperature_c      : { value: float, band: enum(very_cold|cold|comfortable|warm|hot|very_hot) }
season             : enum (winter_dry / pre_monsoon / monsoon / post_monsoon / winter_humid)
                     India-specific seasons
env_severity       : enum (NONE / SOFT_ENV / HARD_ENV / BLOCK_ENV)
env_stress_score   : int 0–100 (composite, advisory)
applied_overrides  : list[ override_id from shared layer ]
ttl_seconds        : int (default 900 — 15 min cache)
```

### `ProductSummary` (LL2 → HLHP)

```
product_id         : UUID
brand              : str
name               : str
category           : enum
declared_types     : list[ skin_type ]
primary_concern    : str
key_actives        : list[ { inci: str, position: int } ]
vehicle            : { hydration_state: enum, continuous_phase: enum, texture: enum, finish?: enum }
comedogenic_risk   : enum (low / moderate / high)
fungal_acne_safe   : bool
last_user_score    : { score: int, band: str, scanned_at: timestamp } | null
```

### `ScanLogEntry` (shared)

```
log_id             : UUID
user_id            : UUID
scan_type          : enum (LL2_PRODUCT_SCAN / HLHP_ALERT_DELIVERED)
product_id         : UUID | null   (for LL2 scans)
profile_snapshot   : JSON          (frozen at scan time)
env_snapshot       : EnvironmentContext  (always present)
ll2_result         : JSON | null   (engine breakdown if LL2 scan)
hlhp_alerts        : list[ { factor, band, alert_short_rendered } ]
composed_verdict   : { band: str, tile_4_addition: str, severity: str }
user_feedback      : enum (none / up / down) | null
post_scan_action   : enum (add_to_cart / explore_more / dismissed) | null
created_at
retention_class    : enum (active / anonymise_pending / anonymised)
```

### `OverrideLayer` (shared service)

```
override_id        : str
applies_to         : list[ engine ]    # ["ll2", "hlhp"]  or ["ll2"]  or ["hlhp"]
trigger            : JSON              # phenotype + season + region predicates
effect             : JSON              # weight delta, ceiling delta, copy adjustment
version            : str (semver)
signed_off_by      : str (Dr. Sarkar / Dr. Banodkar / both)
active_from, active_until
```

---

## 9. Composed user surfaces

What the user actually sees when both engines are active. Two scenarios anchor the
design.

### Scenario 1 — Product scan on a high-stress day

User in Mumbai, monsoon afternoon (RH 85%, temp 32°C, AQI 110). Scans a heavy
ceramide-rich night cream. User is oily-acne-prone, primary concern *acne*.

**Tile 1 (Score):** 48 / Low Match. Score ring animates to amber.
**Tile 2 (What works):** Ceramides at positions 6 and 9 do support barrier — useful
on overnight repair if dry patches form.
**Tile 3 (Falls short):** Vehicle is occlusive-rich; for oily-acne skin this can trap
sebum and worsen fungal-acne risk. Today's high humidity makes that risk meaningfully
higher.
**Tile 4 (Worth knowing today):** Humidity is very high today (85% RH). Even users
who like heavy creams in winter often find them uncomfortable in monsoon. Worth
trying once the season shifts.
**Tile 5 (Unmet needs):** Doesn't address acne — your primary concern. From your
shelf: your X gel-cream (LL band: Good) is a better fit for today's air.

The score is set by LL2's existing math; the environmental ceiling tightened it
further. Tile 4 is HLHP-driven. Tile 5's "from your shelf" line uses Touchpoint E.

### Scenario 2 — HLHP morning alert

User opens the app on a Delhi morning, UVI 11, AQI 280.

**Alert card:** *"UV is extreme today. Indian skin gets about 45 minutes of midday
sun before pigment cells make more melanin than they can clear. If your outdoor time
today is long, broad-spectrum SPF 30+ PA+++ is highly recommended — two fingers on
face and neck before stepping out, reapply every 2 hours outdoors."*

**Pollution sub-card:** *"PM2.5 is high today. If your commute or outdoor time is
long, layer a 10–15% vitamin-C serum and a thorough cleanse afterwards. From your
shelf: your Y serum (LL band: Great, scanned 2 months ago) is your best protective
layer."*

The alert body is from the HLHP workbook; the personalised product line is from
Touchpoint E.

### What does **not** change visually

The 5-tile LL2 carousel is the same shape. The integration adds *content* to Tile 4
and Tile 5; it does not add a sixth tile, a second score, or a "weather widget."
Likewise, HLHP's alert format stays the same; product references appear inline, not
as a separate panel.

---

## 10. The shared override layer

The single most important architectural decision. Without it, the integration is
unsafe.

### Why one layer

LL2 already maintains overrides for *dehydrated-oily*, *mature*, *barrier-compromised*,
*acne-prone separately from oily*, and *seasonal* (Apr–Jun, Jul–Sep, Nov–Feb). HLHP
has its own region/season/climate overrides — monsoon, dry winter, metro pollution,
hill stations. If both engines apply their own overrides during a composed scan,
the user's effective override is *both stacked*. The combined effect can over-correct
to the point of producing dermatologically incorrect output.

A single shared override service prevents this.

### What the override service owns

- The phenotype list (dehydrated-oily, mature, barrier-compromised, acne-prone,
  fungal-acne-flagged, sensitive — defined in LL2, used by both).
- The seasonal calendar (India-specific: winter dry · pre-monsoon · monsoon ·
  post-monsoon · winter humid).
- The region tiers (metros · tier-2 · tier-3 · hill stations · coastal · desert
  belt).
- The override matrix: which (phenotype × season × region) combinations modify
  which engine outputs.
- The versioning, sign-off audit trail, and rollback path.

### What it does *not* own

The override layer **does not score** anything. It returns a list of `applied_overrides`
to each engine, which the engine consumes via its own rules. The override service is
a metadata service, not a scoring service.

### Build sequence

This service is **a Phase 5 deliverable** (§14). Until then, LL2 keeps its existing
overrides and HLHP runs with simple region+season defaults. The composition logic
in §6 and §7 is intentionally conservative until the shared layer ships, to prevent
double-counting.

---

## 11. Latency & reliability

### Latency budget

| Phase | Today (LL2 alone) | With HLHP integration |
|---|---|---|
| Identity + profile load | ~200ms | ~200ms |
| Safety + suitability + observational engines | ~150ms total | ~150ms (env ceiling adds <10ms) |
| HLHP env fetch | n/a | ~150ms (parallelised with engines) |
| Claude tile generation | 2–4s (Sonnet 4.6) | 2–4s (unchanged) |
| Render + log | ~100ms | ~100ms |
| **User-perceived total** | ~2.5–4.5s | ~2.5–4.5s |

The hard rule from §3 — *integration must not add more than 300ms p95* — is achieved
by **parallelising the HLHP env fetch with the LL2 engine pipeline.** The env context
arrives before the suitability engine needs it; if it doesn't, suitability runs
without env modulation and logs the timeout.

### Reliability ladder

Both engines inherit LL2's existing retry pattern:

| Layer | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Claude tile generation | Sonnet 4.6 | Haiku 4.5 | Deterministic template |
| HLHP env feed | Live API | Cached (≤15min stale OK) | Seasonal-default vector (`{region, month}` → median bands) |
| Shared override service | Live | Cached (≤24h) | Global defaults (no overrides applied; logged) |
| Cross-engine lookup (E) | Live LL2 history | Stale (≤7 days) | Generic product-type alert |

The seasonal-default vector for HLHP is important — it lets the integration ship
useful alerts even when the live environmental feed is unavailable, by using regional
seasonal medians (e.g. *"Delhi, January, typical: UVI 5, AQI 250, RH 35%, temp 12°C"*).

---

## 12. Cold-start & graceful degradation

| Missing input | Effect |
|---|---|
| No user profile | LL2 cannot run — falls back to ingredient-lookup (LL1.0 behaviour). HLHP runs with location-only context, alerts are non-personalised. |
| No location | HLHP falls back to "India national defaults" — useful for severe days everywhere (UVI/AQI national alerts). LL2 runs without env context. |
| No LL2 scan history | HLHP alerts use generic product-type recommendations (e.g. *"a 10–15% vitamin-C serum"*), not personalised shelf lookups. |
| LL2 unavailable | HLHP runs as today; product references suppressed. |
| HLHP unavailable | LL2 runs as today; no env context; Tile 4 uses only the static observation library. |
| Override service unavailable | Both engines fall back to global defaults. Composed verdict footnoted as "degraded mode" in the scan log. |

Cold-start is **graceful in both directions** — the integration is additive
intelligence, never a hard dependency. A user with no profile can still get HLHP
alerts. A user with no location can still get a full LL2 scan.

---

## 13. Auth, privacy, DPDP

The integration inherits LL2's DPDP discipline and adds three privacy considerations
specific to combining the two surfaces.

### Inherited from LL2

- **WhatsApp OTP only.** One account spans both features.
- **Phone numbers hashed.** Raw value not retained after OTP verification.
- **Indefinite retention for analytics**, with **progressive anonymisation after 2
  years inactive.**
- **Versioned consent at signup.** Users can export and delete scan history.

### Integration-specific

1. **Location capture is explicit, granular, and consent-gated.**
   HLHP needs location to fetch the right environmental feed. The default is
   **city-level**, not GPS. Exact-coordinate capture is opt-in only and used only
   for sub-city pollution variation (Mumbai south vs north, Delhi NCR vs central).
   Consent for exact coordinates is requested separately from the base signup
   consent.

2. **The combined scan log is more sensitive than either alone.**
   An env-stamped LL2 scan log reveals, over time, the user's typical location, their
   commute pattern (scans clustered by time), and their skincare behaviour. Tighter
   retention discipline:
   - Env stamps anonymised at 12 months inactive (faster than the 2-year general
     rule).
   - Location stripped to region (not city) at 12 months inactive.
   - The full combined log is available to the user for export and deletion at any
     time.

3. **Cross-engine lookups (Touchpoint E) are server-side only.**
   When HLHP references *"your X serum"*, the LL2 history lookup happens in the
   backend. The HLHP client never receives the full LL2 catalogue or scan history —
   only the named product reference for the current alert.

All three additions are subject to clinical and legal sign-off before launch.

---

## 14. Phased rollout

Six phases over an estimated 18–24 weeks after LL2.0 ships. Phases 1–2 are read-only
and low-risk; phases 3+ require sign-off on environmental ceilings and the shared
override layer.

| Phase | Scope | Sign-offs gated by |
|---|---|---|
| **1 — Loose coupling MVP** | Both engines independently. Shared user profile. HLHP shows generic product-type alerts. LL2 ignores env context. Combined scan log starts here. | None beyond LL2.0 launch. |
| **2 — HLHP enrichment of Tile 4** | HLHP env context flows into LL2 (Touchpoint A). LL2's Tile 4 ("Worth knowing today") adds env-aware lines from the HLHP evidence base. No score modulation yet. | Tile copy review by clinical sign-off. |
| **3 — Environmental ceiling integration** | Env ceiling enters LL2's score math (§6). Score can tighten on adverse days. Phase 3 threshold values signed off; default off behind a flag for ramp. | Env ceiling table values; band-shift impact A/B reviewed. |
| **4 — Cross-engine product recommendations** | HLHP alert surfaces call LL2 history (Touchpoint E). *"From your shelf"* lines go live. | Privacy review of server-side lookup pattern. |
| **5 — Shared override layer** | Single override service stands up; both engines migrate to read from it. India phenotype + season + region overrides unified. | Clinical re-sign-off on the unified override matrix. |
| **6 — Composed surfaces (shelf, routine, replenishment)** | "Your monsoon-ready routine" / "Your winter routine" / smart replenishment surfaces. Heavy use of touchpoints A + E. | UX research with target users; PRAC sign-off on category-aware suggestions. |

Sequence is deliberate — phases 1–4 prove the value to users *before* the heavy
override-layer refactor, which is expensive and clinical-sign-off-heavy.

---

## 15. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Double-counted India overrides** (LL2 phenotype + HLHP region both fire) | High pre-phase-5 | Compose phases 1–4 conservatively — only one override layer active per scan. Single shared service in phase 5 closes the gap. |
| **Engine disagreement** (LL2 says Great × HLHP says HARD_ENV) | Medium | UI absorbs both via Tile 4 amplification; never contradicts in Tile 1. §7 composition rules formalise this. |
| **Latency creep** | Medium | Parallel HLHP fetch + env-context cache (15min) + hard p95 guardrail of +300ms. Auto-disable env modulation if fetch slow. |
| **Recommendation drift** ("buy this because of the weather") | Medium | Composition prose reviewed against the *"score informs, you decide"* principle. Clinical sign-off on Tile 4 copy template. |
| **Combined-log privacy compound exposure** | Medium | Faster anonymisation (12 vs 24 months) on env stamps and location. Server-side cross-engine lookups only. |
| **Cold-start UX** (new user gets confusing reduced experience) | Low | Explicit graceful-degradation paths in §12; reduced-mode messaging tested with users. |
| **HLHP feed outage during major UV/AQI events** (worst-case timing) | Low–medium | Seasonal-default vector ensures alerts still useful; outage banner if feed >2h stale. |
| **Drift in HLHP evidence base** (new findings contradict shipped thresholds) | Ongoing | Workbook is the single source of truth; thresholds reviewed quarterly; gaps/conflicts sheet flags disagreements. |
| **LL2 launch slips** | Medium | Integration phases 1–2 are independently shippable if LL2.0 lands first; phases 3+ depend on LL2 stable. |
| **Few-shot voice drift** (one demographic in LL2 prompt — known LL gap) | Inherited | Resolve before phase 2; add a second few-shot profile that includes an env-aware Tile 4 example. |

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **Composed scan** | A LabelLooker product scan in which HLHP environmental context modulates the result and/or Tile 4 |
| **Environmental ceiling** | An additional ceiling on the LL2 score driven by HLHP's environmental severity. Tightens only; never lifts. |
| **Env context object** | The structured payload HLHP passes into LL2 inside a composed scan. Schema in §8. |
| **Severity ladder** | The four-level BLOCK/HARD/SOFT/NONE schema, extended by HLHP with the `_ENV` suffix variants |
| **Shared override layer** | Single source-of-truth service for phenotype × season × region overrides used by both engines |
| **Touchpoint** | A defined data-flow path between the two engines; five of them are defined in §5 |
| **Cross-engine lookup** | An HLHP alert referencing a product from the user's LL2 history (Touchpoint E) |
| **Combined scan log** | The shared, env-stamped log of every LL2 scan and every HLHP alert delivery |
| **Composed verdict** | The user-visible verdict assembled from both engines — a banded LL2 score plus Tile 4 environmental amplification |
| **Cold-start** | The case where one or more inputs (profile, location, history) are missing, and the integration must degrade gracefully |
| **HLHP** | Hyperlocal Health Profile — SkinBB's environmental skincare alerts engine |
| **LL2.0** | LabelLooker 2.0 — SkinBB's personalised ingredient evaluator |
| **PRAC** | Product Review & Approval Committee — SkinBB's metadata verification process (LL2 owns this) |
| **DPDP** | India's Digital Personal Data Protection Act |

---

## 17. Authoritative facts index

*If another document — including older HLHP or LabelLooker artifacts — contradicts
these, **these win.***

- For the canonical HLHP-side details (profile schema, trigger bands, per-factor scoring,
  matching engine, fire budget, alert layers, validation gates), read the **HLHP Engine
  Implementation Spec**. This Integration Blueprint does not duplicate those facts.
- The evidence base behind every HLHP alert is **`HLHP_Evidence_Base.xlsx`** — 507 cited
  findings across the six factors, with structured trigger conditions, severity priorities,
  L1 Personalised + L1 Guest alerts, a Glossary sheet, and a Coverage_Matrix sheet.
- The integration is a **composition layer**, not a merger. Both engines remain
  independently auditable, replayable, and rollbackable.
- **HLHP is read by LL2 synchronously inside a composed scan.** LL2 does not call
  back into HLHP during the same request. Reverse-direction lookups (E) are
  asynchronous and happen only in HLHP's own surfaces.
- **Environmental ceiling tightens, never lifts:**
  `final_score = min(raw_score, type_ceiling, environmental_ceiling)`.
  Suitability is still the priority gate.
- **Highest severity wins.** LL2 safety BLOCK trumps any HLHP state. HLHP
  `BLOCK_ENV` adds an outdoor-postponement notice but does not block the product
  score.
- **Severities do not arithmetically accumulate.** Two SOFTs do not promote to HARD.
- **India overrides live in one shared service** (phase 5). Until then, only one
  override layer is active per scan to prevent double-counting.
- **Combined scan log is env-stamped** and retained indefinitely under DPDP, with
  **12-month** anonymisation of env stamps and location (faster than LL2's 2-year
  general rule).
- **Location capture defaults to city-level.** Exact-coordinate capture is opt-in
  only.
- **Cross-engine lookups are server-side only.** The HLHP client never receives the
  full LL2 catalogue or scan history.
- **Latency budget:** integration may not add more than **300ms p95** to LL2's
  existing 2–4s perceived latency. Parallelisation is mandatory.
- **Generation stack stays as LL2 owns it:** Sonnet 4.6 → Haiku 4.5 → deterministic
  template. The composed verdict is rendered in LL2's existing tile-generation call,
  not in a second LLM round-trip.
- **No prescriptive purchase language** in composed surfaces. The composition can
  say *"this matches today's conditions"*; it cannot say *"buy this."*
- **Env severity bands and ceiling values are flagged for stakeholder sign-off**
  before phase 3 ships, alongside LL2's existing band cutoffs.
- **Evidence base for HLHP thresholds:** the workbook
  `HLHP_Evidence_Base.xlsx` — 345 cited findings, 162 India-tagged, source of
  every environmental threshold this integration consumes.

---

*A score informs. **You decide.***
*HLHP × LabelLooker — SkinBB · Integration Blueprint v2 (refreshed against HLHP Engine Implementation Spec v1, post-gap-fill 507-row evidence base)*
