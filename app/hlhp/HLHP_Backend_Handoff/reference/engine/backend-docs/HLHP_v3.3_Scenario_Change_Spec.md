# Proposed Library Changes — Compound Scenarios Index

**File:** `SkinBB_HLHP_Scenario_Library_v3_3.xlsx` → sheet **`8. Compound Scenarios Index`**
**Status:** ☐ PROPOSAL — awaiting editorial sign-off. **No changes have been applied to the library.**
**Reviewers:** Dr. Soma, Dr. Pravin
**Origin:** Surfaced while investigating why the Mumbai-monsoon canonical case routes to C13 instead of C06.

---

## Why this exists

The compound matcher itself is healthy: **20 of 21** scenarios route their own representative reading back to themselves, and **8 of 9** canonical city-days hit their intended scenario. The two exceptions both trace to **cell-level definition errors in sheet 8**, not engine logic. Each is a single-cell edit. Both were prototyped on a throwaway copy and fully verified (results below); the verification copy has been discarded.

---

## Change 1 — C06 "Monsoon Acne Trifecta": Temperature band

| | |
|---|---|
| **Cell** | `8. Compound Scenarios Index'!C7` (column "Temp Band", row C06) |
| **Current** | `hot`  (35–42 °C) |
| **Proposed** | `warm`  (28–34 °C) |

**Current full row (for context):** C06 · Monsoon Acne Trifecta · Temp `hot` · UV `moderate` · AQI `poor` · RH `very_high` · drivers `Humidity, AQI, Temperature` · seasons `Jul–Sep` · cities `Mumbai, Chennai, Kolkata, Pune monsoon`.

**Rationale.** The scenario is explicitly the **monsoon** (season Jul–Sep; cities Mumbai/Chennai/Kolkata/Pune), and its mechanism text reads "Heat, humidity, and pollution combine." But monsoon temperatures in those cities run ~28–32 °C, which is the **`warm`** band (28–34). `hot` (35–42 °C) describes the **pre-monsoon**, not the monsoon. The Temp band is internally inconsistent with the scenario's own season, cities, and intent.

**What it fixes.** A realistic Mumbai-monsoon reading (32 °C, AQI 220, UV 6.5, RH 88%) currently sits 2 band-steps from C06 but only 1 from **C13 "Industrial Belt Day"**, so C13 wins and the user gets industrial-pollution messaging on a monsoon day. Setting Temp → `warm` brings C06 to distance 1 (tied with C13), and C06 wins on scenario order → monsoon correctly routes to C06.

**Side effects (measured, see Verification).** C06 widens: it picks up ~36 monsoon readings from C13, ~30 elevated-AQI coastal-monsoon readings from C07 "Coastal Monsoon Standard", and ~33 readings that previously matched no compound. No reading *leaves* C06 (a `hot` day is still within tolerance of `warm`).

**Editorial question for sign-off.** When AQI is elevated during a coastal monsoon, is the pollution-aware **"Monsoon Acne Trifecta"** the right frame in preference to the cleaner **"Coastal Monsoon Standard" (C07)**? We believe yes, but it is a clinical/messaging call.

**Optional secondary tweak (your call).** After the Temp fix, C06 still *ties* C13 at distance 1 and wins only because C06 precedes C13 in scenario order. If you'd prefer C06 to win outright by distance, also set **UV band `moderate` → `high`** (`D7`). Monsoon UV is genuinely variable (overcast → moderate; break days → high), so this is optional and worth a clinician's view rather than an automatic change.

---

## Change 2 — C21 "Indoor AC Office Hours": Dominant Drivers

| | |
|---|---|
| **Cell** | `8. Compound Scenarios Index'!G22` (column "Dominant Drivers", row C21) |
| **Current** | `Humidity` |
| **Proposed** | `Humidity, Temperature` |

**Current full row (for context):** C21 · Indoor AC Office Hours · Temp `cool` · UV `low` · AQI `satisfactory` · RH `low` · drivers `Humidity` · mechanism "Eight or more hours of AC-conditioned air at 20–35% humidity steadily pulls water from skin…".

**Rationale.** The engine's "dominant factor" is the lowest-scoring (worst) environmental factor. In C21's own conditions, Temperature `cool` (12 pts) and Humidity `low` (12 pts) **tie**, and the tiebreaker (UV › AQI › Temperature › Humidity) picks **Temperature** — which is not in C21's driver list. A compound only matches when the dominant factor is one of its drivers, so C21 fails its own constraint: it never self-identifies (routes to C15 instead) and fires in only **8 of 540** cool-dry readings. This is the same "unreachable scenario" class that C20 was in, via a different mechanism.

**What it fixes.** Adding Temperature to the drivers makes C21 eligible in its own conditions. Self-identification is restored and reachability rises to **128 of 540** sampled cool-dry readings. This is purely an internal-consistency repair — no clinical reinterpretation.

**Side effects (measured).** C21 pulls ~30 readings that previously matched no compound, plus ~9 from C15 "North Indian Winter Dry" and ~3 from C16 "Hill Station Winter" — i.e. cool, dry, indoor-type readings now get the AC-specific cell instead of a winter scenario. Appropriate.

**Risk:** low. This corrects a near-dead scenario; nothing that currently works stops working.

---

## Verification (prototype on a discarded copy)

| Metric | Current v3.3 | With both edits |
|---|---|---|
| Scenario self-identification | 20 / 21 (C21 fails) | **21 / 21** |
| Canonical city-days hitting intended scenario | 8 / 9 (Mumbai → C13) | **9 / 9** (Mumbai → C06) |
| C21 reachability (sampled cool/dry grid) | 8 / 540 | **128 / 540** |
| Mumbai-monsoon distance: C06 vs C13 | C06 = 2, C13 = 1 → C13 | C06 = 1, C13 = 1 → **C06** (on order) |
| Full pytest suite | 392 passed | **392 passed** |
| Mumbai now resolves to | C13 cell | **C06 Oily/Acne** — action `Balance`, risk 5 (canonical-compliant) |

**Blast radius:** across 3,780 weather × profile combinations, **144 routes (~3.8%) change**, all in the intended direction:

- `C13 → C06`: 36 · `single-factor → C06`: 33 · `C07 → C06`: 30 · `C05 → C06`: 3 (Change 1)
- `single-factor → C21`: 30 · `C15 → C21`: 9 · `C16 → C21`: 3 (Change 2)

No route changed in an unrelated direction; no scenario other than C06/C21 gained or lost reachability.

---

## Rollout if approved

1. Edit the two cells in sheet 8 (`C7`, `G22`; optionally `D7`), bump the library to **v3.3.1**.
2. Re-seed: `python seed_library_to_mongo.py --xlsx library_v3.3.1.xlsx --version 1.0.1` (uses the corrected seeder).
3. Re-run `pytest tests/` (expect 392) and, if desired, the differential sweep to reconfirm blast radius.
4. No engine code change is required — both fixes live entirely in the library.

## Alternative considered (not recommended)

These could instead be "fixed" in the engine — e.g. weighting match specificity, or replacing the "dominant = worst-scoring factor" proxy so C21's driver list wouldn't matter. That's a larger architectural change with broad blast radius. The cell-level library edits are minimal, targeted, and verified, so they're preferred.

---

## Sign-off

| Reviewer | Change 1 (C06 Temp → warm) | Change 1 optional (UV → high) | Change 2 (C21 +Temperature) | Date |
|---|---|---|---|---|
| Dr. Soma | ☐ approve ☐ reject | ☐ approve ☐ reject | ☐ approve ☐ reject | |
| Dr. Pravin | ☐ approve ☐ reject | ☐ approve ☐ reject | ☐ approve ☐ reject | |

*Prepared as documentation only — no library or engine files were modified for this spec.*
