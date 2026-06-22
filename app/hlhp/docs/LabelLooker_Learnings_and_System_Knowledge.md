# LabelLooker — Learnings & System Knowledge
> **A portable, self-contained knowledge document.** Drop this into any project to give a
> reader (human or AI) full working context on the LabelLooker programme: what it is, how it
> is built, the decisions that are locked, the reusable patterns worth lifting into other
> features, and the domain facts that must not be gotten wrong.
>
> It does **not** depend on any other file being present. Where it compresses a larger spec,
> it says so.

| | |
|---|---|
| **Product** | LabelLooker — SkinBB's personalised skincare ingredient evaluator |
| **Parent brand** | SkinBB (Skin Beyond Borders), India |
| **LL1.0** | Live since 16 Oct 2024 — ingredient lookup powered by Ingredipedia |
| **LL2.0** | Spec complete · build-ready — personalised 5-tile match analysis |
| **Owner** | Ajit Marathe (Product); SkinBB co-founder dermatologists (clinical sign-off) |
| **Operating principle** | *A score informs. You decide.* |

---

## 0. How to use this document

It serves four destinations at once; read the lens that applies to you.

- **As AI context in another Claude Project** → §16 (Authoritative Facts Index) is the
  contract: if any other document contradicts those figures, the figures here win. The rest
  is background that should not be contradicted.
- **For a sibling SkinBB feature** (HLHP environmental alerts, gamification, hair care) → §11
  (Reusable Patterns) is written for you. It abstracts the architecture into patterns you can
  lift without re-reading the whole system.
- **For a new engineer onboarding** → read §4–§10 top to bottom; that is the system.
- **As a general reference** → §13 (Domain Accuracy) and §15 (Glossary) stand alone.

---

## 1. What LabelLooker is

LabelLooker turns a skincare product's ingredient list into a **personalised verdict** about
whether it suits *this* user. It is free, India-first, reads any product label (not only
products sold on SkinBB), and is **deliberately not a recommendation engine**. The brief: help
an Indian consumer understand what is in a product and whether it suits them, *without* slowing
the purchase decision.

The numeric score and the structural analysis come from **three deterministic engines**
(Safety, Suitability, Observational). **Claude writes the prose** that the user reads. The
engines decide; the model never does.

### LL1.0 vs LL2.0

| Dimension | LabelLooker 1.0 | LabelLooker 2.0 |
|---|---|---|
| Question answered | What's in this product? | Does this product suit *me*? |
| Output | Ingredient list + plain-language function data | 5-tile personalised verdict carousel |
| Personalisation | None — same answer for everyone | Skin profile drives score and prose |
| Scope | Any product (ingredient-based) | SkinBB-listed products at first launch |
| Foundation | Ingredipedia (VESCOP) | Ingredipedia + PRAC metadata + 3 engines |
| AI usage | None — static database lookup | Claude generates the natural-language tiles |
| Status | Live since Oct 2024 | Spec complete, in build |
| Monetisation | Free, no auth | 5 free lifetime scans, then ₹99 for 10 (no expiry) |

**One-line positioning:** the first ingredient-evaluation tool built by an Indian skincare
platform as a duty to Indian consumers — free, accessible anywhere in India, reads any product,
and explicitly not a pro-sales recommendation engine.

---

## 2. Parent context: SkinBB

SkinBB (Skin Beyond Borders) is an Indian skincare and beauty platform. LabelLooker is one of
its flagship consumer-facing surfaces.

| Person | Role |
|---|---|
| **Dr. Soma Sarkar** | MBBS, MD (Dermatology) — co-founder, clinical sign-off on **safety** rules |
| **Dr. Pravin Banodkar** | MBBS, DNB (Dermatology) — co-founder, clinical sign-off on **scoring** rules |
| **Supriya Marathe** | Head of Digital Marketing — co-founder, commercial & brand |
| **Ajit Marathe** | Founder / product owner — architecture & editorial direction |

**PRAC (Product Review & Approval Committee).** Every product listed on SkinBB passes through
PRAC, which verifies declared metadata — suitability, concerns addressed, benefits delivered.
That declared metadata is what LL2.0 scores against. This is *why* the listed-products-only
launch scope works: trust verified upstream data, skip the ingredient-inference layer an
off-platform analyser would need.

> **PRAC is a process/validation concept only.** It is **not** a scoring parameter. (An earlier
> "PRAC baseline" scoring weight existed and has been **removed** — see §6.)

**Ingredipedia & VESCOP.** Ingredipedia is a 1,000+ entry personal-care ingredient knowledge
base co-developed with **VESCOP — Vivekanand Education Society's College of Pharmacy, Chembur,
Mumbai**. It is the factual foundation under both LL1.0 and LL2.0. VESCOP is the academic
partner; credit it accurately by full name and do not overstate the relationship.

**Conservatism by design.** Every clinical claim, scoring threshold, and safety rule must
survive review by the co-founder dermatologists. When evidence is unclear, LL2.0 says so. When
the formula disagrees with the label, LL2.0 notes it without telling the user what to do.

---

## 3. Product philosophy (non-negotiable)

These are positioning commitments, not preferences. Breaking them breaks the product's reason
to exist.

1. **A score informs; the user decides.** No prescriptive "buy this / don't buy this." The tool
   surfaces fit and lets the user choose.
2. **Not a pro-sales engine.** It reads any product, including ones SkinBB doesn't sell, and
   will tell a user a SkinBB-listed product is a poor match for them. Integrity over conversion.
3. **Don't slow the decision.** The experience is decision-oriented, one idea per screen, with
   depth available only on demand.
4. **Factual positioning, no fabricated narratives.** No composite anecdotes or invented
   customer stories in editorial content. The honest framing: existing tools were pro-sales,
   LabelLooker-style tooling was absent in India, SkinBB had the capability and built it.

---

## 4. System architecture

Six layers. Deliberately familiar shapes (REST + PostgreSQL + stateless services) so the
novelty stays concentrated in the **engine** and **generation** designs.

| Layer | Component | Owns |
|---|---|---|
| Client | LL2 badge + result modal | Entry point, loading state, animated score ring, 5-tile carousel, full-analysis drawer |
| Gateway | API Gateway | Auth middleware, session validation, credit-balance checks, rate limiting, schema validation. Two endpoints: `/ll2/profile` (signup + top-up), `/ll2/score` (the scan) |
| Services | Profile Service | OTP lifecycle, session tokens, profile top-up logic (which fields are still missing). The one **stateful** service |
| Services | Scoring Orchestrator | Engine invocation order, ceiling & band rules, `MatchResult` assembly. **Stateless** — scales horizontally |
| Services | Generation Service | `build_prompt()`, Claude call with cached system prompt, `parse_response()`, retry ladder, template fallback |
| Engines | Safety / Suitability / Observational | Deterministic scoring (see §5) |
| Data | Product Catalog (Postgres) | PRAC-verified metadata, INCI lists, pre-computed match scores for "explore more" |
| Data | Observation Library (Postgres) | Versioned rules with triggers, P1–P4 priority, `editorial_text` |
| Data | Scan Logs (Postgres) | One row per scan: profile snapshot, engine breakdown, tile content, feedback, post-scan action |
| External | Claude API | Tile prose (Sonnet 4.6 primary, Haiku 4.5 fallback); system prompt cached |
| External | WhatsApp Cloud API | OTP dispatch & verification |
| External | Razorpay | Credit-pack purchases |

### The 10-step scan

Steps 1–4 identify the user and shape the request; 5–8 are the scoring pipeline; 9–10 produce
output.

1. **Trigger** — user taps the LL2 badge on a product card.
2. **Identity** — WhatsApp OTP if no session; silent login if returning.
3. **Profile load** — required fields validated; missing fields prompt a top-up.
4. **Request shaped** — profile snapshot + `product_id` submitted to the orchestrator.
5. **Safety engine** — `BLOCK`/`HARD` short-circuits the flow.
6. **Suitability engine** — type match, concerns (55%), benefits, ceiling.
7. **Ceiling & band** — `final_score = min(raw_score, type_ceiling)`.
8. **Observational overlay** — top 1–2 observations selected (~120 ms).
9. **Prose generation** — Claude renders all five tiles from the structured result. **Dominant
   latency cost, 2–4 s.** Everything else combined is under half a second.
10. **Render + log + feedback** — modal animates in, `scan_logs` row written, thumbs up/down
    rendered (no modal, no friction).

---

## 5. The three scoring engines

Three concerns, three independent engines, fixed order — **safety → suitability →
observational**. Each is deterministic, configurable, and emits a structured result the
orchestrator assembles.

### Engine 01 — Safety (runs first)

Five parallel rule families evaluate the profile against the formula: **life stage**
(pregnancy, nursing, minor), **allergies**, **conditions** (rosacea, eczema), **medications**
(e.g. isotretinoin interactions), **age**. Highest-severity outcome wins.

| Severity | Behaviour | Example |
|---|---|---|
| `BLOCK` | Short-circuit — exit immediately, no score shown | Pregnancy + retinoid |
| `HARD` | Exit with override option | Rosacea + alcohol denat in top 10 |
| `SOFT` | Continue scoring, flag for Tile 4 | Sensitivity + fragrance |
| `NONE` | Continue normally | No safety flags fired |

### Engine 02 — Suitability (the scoring core)

Compares the user profile against PRAC-declared product metadata and applies a **hard score
ceiling** based on skin-type match. This is the engine that makes *"a well-built dry-skin
moisturiser still scores low for an oily-skin user"* true.

| Match level | Source | Points | Ceiling |
|---|---|---|---|
| `EXACT` | User type ∈ `product.declared_types` | 35 | 100 |
| `ADJ` (adjacent) | Adjacency matrix (e.g. Oily ↔ Combination) | 17 | 80 |
| `OPP` (opposite) | Hard opposite (e.g. Oily ↔ Dry) | 0 | 55 |

Concern match contributes the largest share (55% — see §6). Benefit alignment contributes a
smaller fixed amount. **Sensitivity is a modifier on the base type, not a base type itself.**

### Engine 03 — Observational (editorial overlay)

Runs after scoring; produces Tile 4 ("Worth knowing"). Four prioritised rule families:

| Family | Watches for | Example trigger |
|---|---|---|
| **M — Marketing** | Label-claim vs actual-formula mismatch | "Kakadu Plum" hero in marketing while the real active is ethyl ascorbic acid at position 2 |
| **U — User-specific** | Combinations warranting caution for this profile | 10% niacinamide, first-time user → introduce gradually |
| **F — Formulation** | Construction quirks worth flagging | Heavy emollient stack in a product marketed as oil-free |
| **C — Category** | Category conventions & edge cases | Sunscreen filter combinations needing re-application warnings |

Each observation has versioned, pre-written `editorial_text` in the Observation Library. The
engine selects the top 1–2 by **family priority** and **band-state amplification** — e.g.
amplify a caution for a Great-band result; suppress one for a Low band where Tile 3 already
carries the honesty.

---

## 6. Scoring math: weights, ceilings, bands

> **AUTHORITATIVE WEIGHT SET.** Concerns axis = **55%**, split primary **33%** / secondary
> **14%** / tertiary **8%**. The earlier **35 / 50 / 10 / 5** split (type / concerns / benefits
> / PRAC-baseline) that still appears in some early artifacts — including the master HTML's
> architecture card — is **superseded**. The **PRAC-baseline scoring parameter has been
> removed**; PRAC remains a process/validation concept only.

### Weighted contributions

| Axis | Weight | How it's computed |
|---|---|---|
| Skin type | Variable points + ceiling | EXACT 35 pts·ceil 100; ADJ 17 pts·ceil 80; OPP 0 pts·ceil 55 |
| Concern — primary | 33% | User's top concern vs `product.primary_concern` / benefits |
| Concern — secondary | 14% | User's second concern, same matching |
| Concern — tertiary | 8% | User's third concern, same matching |
| Benefits alignment | Small fixed | Per-benefit bonus when user-stated benefits appear in `product.benefits` |

### The ceiling rule

```
final_score = min(raw_score, type_ceiling)
```

This is what makes suitability the **priority gate**. A perfectly built barrier-repair
moisturiser still lands in the Low band for an Oily user (ceiling 55), no matter how well it
addresses their concerns. **The ceiling does the work, not the raw weights.**

### Bands

| Band | Score | Post-scan CTA |
|---|---|---|
| Great Match | ≥ 85 | Add to cart |
| Good Match | 60–84 | Add to cart with honest caveats |
| Low Match | < 60 | Explore better matches (pre-filtered by user profile) |
| Gate | Safety flagged | See safer options |

> Band cutoffs (85, 60) and ceiling values (100, 80, 55) are **flagged for stakeholder
> sign-off before launch**, alongside Safety-rule INCI lists and the model/caching specifics.

---

## 7. The base-formula scoring module

A separate, engineering-ready axis layered on top of the suitability engine. It exists because
**two products with identical INCI ingredients can behave very differently depending on their
carrier system** — the same niacinamide in a gel-cream vs an oil serum lands differently on
oily, acne-prone skin. This module scores the *vehicle*, separately from the actives.

### Two-axis carrier model

Replaces a single "carrier" enum, because "anhydrous" today conflates lipid balms, silicone
primers, wax sticks, and pressed powders that share nothing on skin.

| Axis | Values | Why it matters |
|---|---|---|
| `hydration_state` | anhydrous / aqueous-thin / aqueous-rich / occlusive | How the product loads water vs lipid onto skin |
| `continuous_phase` | aqueous / silicone / oil / wax | Feel, layering compatibility, pore-occlusion behaviour |

`texture` (a 12-value brand-declared enum) is the **dominant matrix axis**; `continuous_phase`
is a modifier; `finish` (matte / natural / dewy / luminous) is a third axis used only for
makeup-adjacent / primer / sunscreen products — because Indian sunscreen consumers buy on
finish, not SPF (Mintel India Suncare 2024).

### Four validated scoring matrices

Rubric: **Excellent / Good / OK / Poor / Avoid.** "Avoid" is reserved for unambiguous
mismatches (e.g. balm × very-oily acne-prone in summer).

1. **Texture × skin type** — e.g. heavy cream demoted for oily skin in monsoon.
2. **Continuous phase × skin type** — e.g. silicone-continuous slightly demoted for acne-prone
   in high humidity (silicone primers trap sebum + sweat above ~60% RH in Indian heat).
3. **Fragrance × sensitivity** — EU-26 allergen list + curated essential-oil list.
4. **Alcohol × hydration state** — *drying* short-chain/denatured/volatile alcohols only,
   INCI-position weighted. Fatty alcohols (cetyl, cetearyl, stearyl…) are emollients and are
   **never** penalised.

### India-specific override rules (fire after the base matrix)

- **Dehydrated-oily** — penalise high alcohol and over-mattifying. The dominant Indian
  phenotype; standard "oily skin → more astringent" advice makes it *worse*.
- **Acne-prone** (separate from oily) — escalate "Poor" → "Avoid" for heavy textures;
  `comedogenic_risk: high` hard-blocks; `fungal_acne_safe: no` + user-flagged fungal acne →
  Avoid.
- **Mature** — relax rich-texture penalties (but keep fragrance penalty; mature ≠ tolerant).
- **Barrier-compromised** — hard-block fragrance, volatile alcohol, and AHA/BHA-as-vehicle.
- **Seasonal** — Apr–Jun and Jul–Sep favour lighter textures; Nov–Feb relaxes.

### Companion outputs (advisory, not in the main matrix)

- **Position-weighted comedogenic risk** — curated *consensus* offenders only, weighted only
  when in the **top 5 INCI positions**. (Comedogenicity is low-confidence; the rabbit-ear assay
  over-flags. Dilution matters: strong neat comedogens become non-comedogenic when diluted.)
- **`fungal_acne_safe` flag** — C11–C24 free-fatty-acid / ester / polysorbate / fatty-alcohol
  heuristic. **Distinct from comedogenicity.** Surfaced only when the user self-flags fungal
  acne (Malassezia folliculitis).

> Brand-declared "non-comedogenic" claims are stored but **not authoritative** — they do not
> override the derived risk (no standardised testing / regulatory oversight behind the claim).

### Staged rollout

| Stage | Sprints | Scope |
|---|---|---|
| 1 | 1–2 | Core schema, four matrices, two simplest hard-block overrides (acne-prone, barrier-compromised), PRAC validation rules |
| 2 | 3–4 | Override rules (dehydrated-oily, mature, seasonal); finish axis; rationale-strings renderer |
| 3 | 5–6 | Fungal-acne flag with advisory UI; Indian-context overlay copy |

---

## 8. The Claude generation layer

The engines produce structural facts; **Claude turns them into prose**. A Python module
(`ll2_generation.py`) builds and sends the prompt that converts a deterministic scoring result
into the five tile fields.

- **Does:** translate the structured scoring output into warm, precise, editorial prose.
- **Does NOT:** decide the match state, the score, or which ingredients matter — those are
  given by the engines and passed in.

### Configuration

| Setting | Value |
|---|---|
| Model | Claude Sonnet 4.6 primary; Haiku 4.5 retry fallback |
| Temperature | 0.4 — consistent voice without robotic repetition |
| `max_tokens` | 800 cap (outputs typically ~400) |
| Caching | Static system prompt cached via Anthropic prompt caching to cut cost |
| Output | JSON: `verdict`, `works`, `falls_short`, `falls_short_tone`, `worth_knowing`, `covered_message` |
| Fallback ladder | Sonnet → Haiku → template-based text on schema failure (logged) |

### The five output fields

| Field | Voice | Tile |
|---|---|---|
| `verdict` | One-line summary, italic-quote feel | 1 (under the score) |
| `works` | Specific, ingredient-named, position-cited | 2 |
| `falls_short` | Honest, tone-calibrated (positive / caution) | 3 |
| `worth_knowing` | Single sharp editorial observation | 4 |
| `covered_message` | Only for Great Matches with no unmet needs | 5 |

**Prompt structure:** the **system prompt and few-shot examples are static** (and cached); the
**runtime user prompt is built fresh per scan** from user + product + scoring + observations.
Band-state notes steer tone (e.g. Low band: credit the formulation, never call it a "bad
product"; it may be excellent, just for a different user).

> **KNOWN GAP — fix before launch.** The few-shot examples all use a single demographic (an
> 18-year-old oily-skin female) across the great / good / low examples. Add a **second few-shot
> profile** (e.g. a 45-year-old dry-skin user) to prevent voice drift at edge cases the current
> examples don't cover.

---

## 9. Auth, credits & data retention

| Area | Decision |
|---|---|
| Auth | **WhatsApp OTP only.** No email, no password. One mechanism for signup and returning users |
| Rate limits | **5 free scans per user lifetime**, then **₹99 for 10** additional scans; purchased credits **never expire** |
| Errors | Retry + fallback layer; three failure domains handled separately — Claude, WhatsApp, internal |
| Observability | Log **every** scan with full context; frictionless thumbs up/down on every result |
| Retention | Retain indefinitely for analytics; DPDP-compliant |
| Post-scan | Good or above → Add to cart; Low or Gate → Explore better matches (pre-filtered) |
| Hair care | **Unified engine** with category-aware config; split only if latency/cost data later warrants it |

**DPDP compliance surface (India's Digital Personal Data Protection Act):**

- Phone numbers stored **hashed**; the raw value is never retained after OTP verification.
- A **progressive anonymisation** job strips identifiable fields from accounts inactive for
  **two years**, on a published schedule.
- Users can export and delete their scan history; consent is captured at signup with versioned
  policy text.

---

## 10. Tech stack & design system

**Backend:** FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Redis · PostgreSQL · AWS ECS +
RDS. TypedDict-based Python with full type hints in the generation module.

**Integrations:** Claude API (tile generation) · WhatsApp Cloud API (OTP) · Razorpay (payments).

**Design tokens:**

| Token | Value |
|---|---|
| Background | `#F4EEE2` (paper-cream) |
| Accent | `#D16A42` (coral) |
| Display type | Instrument Serif |
| Body type | DM Sans |
| Code/mono | JetBrains Mono |

---

## 11. Reusable patterns (for sibling features)

The architecture decomposes into patterns that are useful well beyond LabelLooker — directly
applicable to HLHP (hyperlocal health profile / environmental alerts), gamification, hair care,
and any future SkinBB feature. Lift these; you don't need the rest of the system to use them.

1. **Deterministic engine + LLM-as-renderer.** Compute every fact, score, and decision
   deterministically; the LLM only writes prose from a structured result. Buys you testability,
   auditability, cost control, and clinical defensibility — the model can't invent a verdict.
   *Use wherever an answer must be trustworthy and explainable.*
2. **Priority gate with a hard ceiling.** One dominant axis caps the final score regardless of
   how strong everything else is (`final_score = min(raw, ceiling)`). *Use wherever a
   prerequisite should dominate* — e.g. an HLHP environmental hazard capping an "outdoor-OK"
   score no matter how good other conditions are.
3. **Severity short-circuit ladder** (`BLOCK` / `HARD` / `SOFT` / `NONE`). A clean way to gate
   any safety- or risk-sensitive flow: hard stops exit early, soft flags ride along into the
   output. *Directly reusable for environmental alerts.*
4. **Depth-on-demand carousel.** One idea per screen; power-user detail lives in opt-in drawers.
   The carousel is the *floor* of the experience, not a summary of a denser layout. *Use for
   any low-friction consumer surface; matches the target audience's consumption pattern.*
5. **Versioned rule library** with `editorial_text` + priority + band-state amplification.
   Content and logic are governed data, not hardcoded strings; selection is prioritised and
   context-amplified. *Use for any system that surfaces curated guidance.*
6. **Retry ladder with template fallback** (strong model → cheap model → deterministic
   template). Keeps an LLM-in-the-loop feature reliable; if you hit the template path often,
   the real problem is API reliability, not template quality. *Use for any user-facing LLM call.*
7. **Cache the static, rebuild the dynamic.** System prompt + few-shots are static and cached;
   the per-request user prompt is built fresh. *Standard cost pattern for repeated LLM calls.*
8. **India-specific override layer on global defaults.** Start from defensible global rules,
   then apply local overrides (climate, season, phenotype). *Reusable localisation pattern —
   HLHP's UV/AQI/temperature/humidity logic is the same shape.*
9. **Indefinite retention + progressive anonymisation** for DPDP. Keep data for analytics value
   while staying compliant by hashing identifiers and anonymising on an inactivity schedule.
   *Reusable data-governance posture.*
10. **Trust verified upstream data; skip inference.** PRAC-verified metadata lets LL2.0 score
    against declared facts instead of inferring from raw INCI. *Use to scope an MVP: lean on a
    trusted source first, build the inference layer later.*
11. **Category-aware unified engine.** Hair care reuses the same engine via configuration rather
    than a forked codebase; split only when data proves the case. *Avoid premature splitting.*

---

## 12. Key principles & learnings

- **Suitability is the priority gate.** A well-formulated product for the wrong skin type still
  scores low. This single principle is what separates LabelLooker from any "ingredient toxicity"
  scorer. Internalise it first.
- **Depth-on-demand over regression.** New scoring dimensions (like the base-formula module)
  augment the carousel through drawers; they never replace the carousel with a denser layout.
  Per-benefit progress bars and multi-section layouts were explicitly rejected as regressions to
  LL1 patterns.
- **Indian-market specificity throughout.** Matrices validated against Indian dermatology
  consensus (IADVL/IJDVL, PRACT-India 2025); climate-seasonal overrides built in, not bolted on;
  the dehydrated-oily phenotype gets a dedicated override; ~28–37% of Indian users self-identify
  as sensitive (Pandhi et al. 2025), so fragrance and alcohol matrices weight accordingly.
- **Percentages are unreliable on Indian labels.** Active-ingredient percentages must not appear
  in consumer-facing content. Form, vehicle, and ingredient *presence* matter more than claimed
  concentrations; Indian regulation doesn't enforce a standard declaration format, so leaning on
  percentages introduces false precision.
- **Chemistry accuracy is non-negotiable.** The audience is technically literate; a wrong detail
  costs credibility. See §13.
- **Avoid the Yuka/EWG single-score trap.** Don't produce a flat "safety score" that ignores
  percentage and skin-type context; don't equate "presence of a flagged ingredient" with
  "real-world risk"; don't use precautionary "if in doubt, flag red"; don't penalise silicones,
  parabens, or PEGs as a category.

---

## 13. Domain accuracy (must-not-get-wrong)

These are corrections that have been made and must stay made wherever LabelLooker knowledge is
used:

- **Chelating agents** (disodium EDTA, tetrasodium EDTA, sodium phytate, sodium gluconate) bind
  **trace metals within the formulation** for stability and shelf life. They do **not** soften
  household water. Hard-water tolerance in cleansers comes from **surfactant choice** (and water
  filtration), not chelators.
- **"USFDA," not "FDA."** Use the full, correct regulator name throughout.
- **Comedogenicity is a low-confidence, top-of-INCI-only signal** — a curated list of consensus
  offenders weighted only in the top 5 positions, never a per-ingredient additive score.
- **`fungal_acne_safe` is a separate flag** from comedogenicity (C11–C24 heuristic), surfaced
  advisorily only when the user self-flags fungal acne.
- **Drying ≠ pore-clogging.** Denatured/volatile alcohol is penalised for dry/sensitive/
  barrier-compromised (and dehydrated-oily) skin, not treated as a comedogen.
- **Fatty alcohols are emollients** (cetyl, cetearyl, stearyl, behenyl…) — never penalised as
  "alcohol."
- **No fabricated narratives** in editorial content — factual positioning only.

**Reference sources used in the design** (for provenance, not for re-quoting): IADVL/IJDVL
Indian dermatology consensus; Pandhi et al. 2025 (*Frontiers in Medicine*); PRACT-India 2025
(*Antibiotics*); Lab Muffin (Michelle Wong); Beautybrains (Perry Romanowski); Kind of Stephen
(Stephen Alain Ko); Paula's Choice; Mintel India 2024–2025.

---

## 14. Open items & roadmap

**Outstanding stakeholder sign-offs before launch:**

- Score band thresholds (85 / 60) and type ceilings (100 / 80 / 55).
- Safety-rule INCI lists.
- Anthropic model / caching specifics.
- Second few-shot demographic profile in the generation prompt (see §8).
- Related clinical/editorial validation items.

**Build roadmap:** four phases over ~20 weeks with defined critical-path milestones. Base-formula
module ships across three stages (§7). Hair care follows on the unified engine with category-aware
config. Off-platform scanning (barcode / OCR / unverified products) is a deliberate later product
— same engine, different ingestion.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **INCI** | International Nomenclature of Cosmetic Ingredients — the standard ingredient list |
| **PRAC** | Product Review & Approval Committee — SkinBB's metadata-verification process. *Process only, not a scoring parameter* |
| **Ingredipedia** | 1,000+ entry ingredient knowledge base co-developed with VESCOP; the factual foundation |
| **VESCOP** | Vivekanand Education Society's College of Pharmacy, Chembur, Mumbai — academic partner |
| **Tile** | One screen of the 5-screen swipeable result carousel (Score / What works / Falls short / Worth knowing / Unmet needs) |
| **Ceiling** | The cap suitability places on the score by skin-type match; the mechanism behind "right formula, wrong type, still low" |
| **Band** | Great / Good / Low / Gate — the score range that drives the post-scan CTA |
| **HLHP** | Hyperlocal health profile — SkinBB's environmental-alert feature (UV / AQI / temperature / humidity) |
| **DPDP** | India's Digital Personal Data Protection Act |

---

## 16. Authoritative facts index

*If another document — including older LabelLooker artifacts — contradicts these, **these
win.***

- Concerns axis weight = **55%** → primary **33%**, secondary **14%**, tertiary **8%**.
- The **35 / 50 / 10 / 5** weight set is **superseded**. The **PRAC-baseline scoring parameter
  is removed**; PRAC is process/validation only.
- Type match points / ceilings: EXACT **35 / 100**, ADJ **17 / 80**, OPP **0 / 55**.
- `final_score = min(raw_score, type_ceiling)`.
- Bands: Great **≥ 85**, Good **60–84**, Low **< 60**, Gate (safety-flagged).
- Safety severities: `BLOCK` (no score) · `HARD` (override option) · `SOFT` (continue + flag) ·
  `NONE`.
- Generation: Sonnet 4.6 primary → Haiku 4.5 fallback → template; temp **0.4**; `max_tokens`
  **800**; system prompt cached; fields `verdict` / `works` / `falls_short` (+`falls_short_tone`)
  / `worth_knowing` / `covered_message`.
- Auth: **WhatsApp OTP only.** Credits: **5 free lifetime → ₹99 for 10, non-expiring.**
- Retention: indefinite for analytics; DPDP via consent, phone hashing, progressive
  anonymisation after **2 years** inactivity.
- Base-formula carrier model is **two-axis**: `hydration_state` × `continuous_phase`.
- Chelators bind **trace metals in-formula** (stability), not household water.
- No active percentages in consumer content. "USFDA," not "FDA."
- Launch scope: **SkinBB-listed products only**; off-platform scanning is a later product.
- Known gap: generation few-shots use **one** demographic; a **second profile** is needed before
  launch.

---

*A score informs. **You decide.***
*LabelLooker 1.0 & 2.0 · SkinBB*
