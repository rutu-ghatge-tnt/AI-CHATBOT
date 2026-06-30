# SkinBB HLHP v3.3 — Full Review / Audit

**Scope:** Excel scenario library (`SkinBB_HLHP_Scenario_Library_v3_3.xlsx`), routing engine (`hlhp_engine.py`), Mongo seeder (`seed_library_to_mongo.py`), test harness (`mock_cache.py`, `conftest.py`, 4 test files).
**Method:** static read + dynamic verification in a sandbox — ran the full suite, ran the seeder's builders against the real workbook, and scanned all 1,610 library rows / 4,830 alert strings directly.
**Headline:** the test suite is green (392 passed, exactly as documented) but it runs entirely through `mock_cache`, so it does **not** exercise the production seeder — which is broken. Tests passing ≠ production works.

---

## Findings at a glance

| # | Severity | Area | Issue |
|---|----------|------|-------|
| 1 | **Critical** | Seeder | `build_scenario_cells` crashes (`IndexError`) — phantom "points" column; production Mongo never gets the 750 single-factor cells |
| 2 | **High** | Engine + library | Scenario **C20** is permanently unreachable; 35 cells are dead content |
| 3 | **Medium** | Engine | Guest vs full-profile **dominant-factor tiebreaker** differ → divergent output for identical weather |
| 4 | **Medium** | Library | L2 explainers don't meet the stated **60–90 word** spec (83% are short); CI doesn't enforce it |
| 5 | **Medium** | Engine | `debug` diagnostics returned on **every** production full-profile response |
| 6 | **Low** | Engine | Zero-factor override double-counts / one-tier cap; hard `motor`/`redis` import |
| 7 | **Low** | Tests | Systemic blind spots: seeder untested, content lint not exhaustive, narrow profile sweep |

What's solid (verified): band classification exactly matches the Bands Reference sheet; the master grid is complete (750) and free of duplicate keys; compound (630) and guest (230) counts are complete; skin types/concerns match the engine enums; modifier tables parse correctly; and jargon/brand discipline holds across **all** 4,830 alert strings (0 hits).

---

## 1 — CRITICAL: the seeder can't load single-factor cells

`seed_library_to_mongo.py → build_scenario_cells()` maps the Master Library as if it had a **"points" column at index 5** and an 19th column at index 18:

```python
"band_key": row[4],
"points":   row[5],     # <-- no such column in Master Library
"skin_type":row[6],     # everything from here is shifted by one
...
"india_context": row[18],  # <-- index 18 doesn't exist (sheet has 18 cols, 0..17)
```

The Master Library has **18 columns** (`A..R`): `ID, Factor, Band, Range, Band Key, Skin Type, Concern, Risk, Risk Level, Confidence, Evidence, PMID, L0, L1, L2, Action, Zones, Cities`. There is no points column. Running the builder against the real workbook:

```
FAIL scenario_cells  -> IndexError: tuple index out of range
OK   compound_cells       -> 630 docs
OK   guest_cells          -> 230 docs
OK   compound_scenarios   -> 21 docs
OK   age_modifiers        -> 36 docs
OK   gender_modifiers     -> 24 docs
OK   zones                -> 6 docs
OK   band_definitions     -> 25 docs
```

`scenario_cells` is built **first** in `main()`'s dict literal, so the whole seed aborts before any write — even with `--dry-run`. Production MongoDB therefore gets **zero** single-factor cells, breaking the full-profile single-factor path and every per-factor lookup (`get_cell`).

Why the tests don't catch it: `mock_cache.py` uses the **correct** 18-column mapping (no points field). The suite loads the library through the mock, so all 392 tests pass while the real seeder is broken. This is a test/prod divergence.

**Fix:** delete the `points` field and shift indices 6→5 … 17→16, drop `row[18]`, so the mapping matches `mock_cache.py`:
`skin_type=row[5], concern=row[6], risk=row[7], risk_label=row[8], confidence=row[9], evidence.summary=row[10], anchors=parse_pmids(row[11]), L0=row[12], L1=row[13], L2=row[14], action_cluster=row[15], applicable_zones=row[16], india_context=row[17]`. (The compound, guest, scenario, modifier, zone, and band builders are all mapped correctly.)

---

## 2 — HIGH: scenario C20 "AC Transition Stress" is unreachable

In `8. Compound Scenarios Index`, C20's bands are `Temp=cool, UV=any, AQI=any, RH=very_low` — only **2 concrete bands**. But `find_compound_match()` requires `match_count >= 3` (bands set to `any` are skipped). So C20 can never satisfy the matcher and is never selected.

Consequence: its **30 compound cells** (sheet 9) + **5 guest compound cells** (sheet 11) = 35 rows are dead weight. C21 "Indoor AC Office Hours" (4 concrete bands) already covers the AC use-case. Verified: a reading that hits C20's two concrete bands routes to a different scenario, never C20.

**Fix (pick one):** give C20 a 3rd concrete band; or relax the `match_count` threshold for low-specificity scenarios; or retire C20 and remove its cells.

---

## 3 — MEDIUM: guest vs full-profile tiebreaker inconsistency

Full-profile path (`route`, step 4) breaks score ties with `FACTOR_TIEBREAKER = [UV, AQI, Temperature, Humidity]`. The guest path instead does:

```python
sorted_factors = sorted(points.items(), key=lambda x: x[1])
dominant_factor, _ = sorted_factors[0]   # ties resolve by dict order: Temp, AQI, UV, Humidity
```

So when the worst factor is a tie, full-profile picks **UV** but guest picks **Temperature**. Verified with `T=45 (extreme_heat, 0pts)` and `UV=12 (extreme, 0pts)`: full-profile `dominant_factor = UV`; the guest path would select Temperature. For identical weather, a guest and a logged-in user can get different single-factor cells (and different compound eligibility, since the dominant must be in a scenario's `dominant_drivers`).

**Fix:** use `FACTOR_TIEBREAKER` in the guest branch too.

---

## 4 — MEDIUM: L2 explainers miss the stated length spec (and CI doesn't check it)

The column header specifies **"L2 Explainer (60–90w)"**, but an exhaustive scan shows most L2 strings fall short of 60 words:

| Sheet | rows | L2 median | min–max | under 60w |
|---|---|---|---|---|
| 10. Master Library | 750 | 56 | 45–72 | 520 (69%) |
| 9. Compound Cell Library | 630 | 52 | 36–68 | 600 (95%) |
| 11. Guest Mode | 230 | 43 | 30–67 | 223 (96%) |

Overall: **1,343 of 1,610 (83%)** L2 cells are under 60 words; none exceed 90. Minor overages elsewhere: 8 L0 cells >20w (max 22), 23 L1 cells >40w (max 48). The content itself reads well (clear, India-context, no jargon) — a typical L2 is 59 words — so this is a **spec-conformance** gap, not a quality problem.

CI misses it because `test_l2_substantive_length` only asserts `>= 40` words on **one** cell, and `test_l0_compact_length` allows `<= 35`. **Fix:** either relax the documented L2 target (e.g. ~45–75w) or expand the L2 copy, and tighten the length tests to the agreed numbers across all cells.

---

## 5 — MEDIUM: debug diagnostics leak into production responses

`AlertResponse.debug` is commented "surface only in dev," but `route()` populates it on **every** full-profile response, and `/v1/alert` returns the model unchanged — so production leaks `dominant_factor`, `bands_observed`, `compound_id`, `compound_distance`, `base_risk`, and modifier evidence. The guest path returns no debug, so the API shape is also inconsistent between paths. **Fix:** gate `debug` behind an env flag / request flag and omit it by default.

---

## 6 — LOW: smaller engine notes

- **Zero-factor override (step 1).** A factor at 0 points already lowers the score (pushing severity down), and then *additionally* escalates the severity band by one tier — arguably double-counting. Also, multiple zero factors still escalate only one tier. This matches the documented design; flagging to confirm it's intentional.
- **Hard `motor`/`redis` import at module top.** `hlhp_engine.py` imports the async drivers on load, so `route()` and the `classify_*` helpers can't be imported anywhere without those packages installed (and they pull in `pymongo`). Consider lazy-importing inside `startup()` so the pure routing logic is reusable/testable standalone.

---

## 7 — LOW: systemic test blind spots

The 392 tests run only through `mock_cache` against 8 fixed sensor reads × 12 profiles (all `Adult`/`Female` in the jargon sweep). They never (a) exercise `seed_library_to_mongo.py` — hides #1; (b) lint all 1,380 cells for length/jargon — hides #4 (though my exhaustive scan found jargon/brands clean); (c) assert the production `LibraryCache` key-building matches the mock; (d) cover most age bands / gender states. **Recommend:** a seed-script load-parity test (assert seeder docs == mock docs per collection) and an exhaustive workbook content lint in CI.

---

## Suggested order of operations

1. Fix the seeder mapping (#1) and add a load-parity test so it can't regress invisibly.
2. Resolve C20 (#2) — likely retire it or add a band.
3. Align the guest tiebreaker (#3) and gate `debug` (#5).
4. Editorial pass: decide the real L2 target and either relax the spec or lengthen copy (#4); same review picks up the two known items (C02 Jaipur Dry→`Calm`, C09 Pregnancy/Melasma→`Maintain`), both reproduced as documented.

---

## Fixes applied (post-review)

Implemented on copies in this folder (`hlhp_engine.py`, `seed_library_to_mongo.py`); the original uploads are untouched. Re-verified: **full suite 392 passed**, plus the targeted checks below.

| # | Fix | Verification |
|---|-----|--------------|
| 1 | Seeder `build_scenario_cells` remapped to the real 18-column layout (dropped the phantom `points` field), now in lock-step with `mock_cache` | Builds **750** docs; **0 mismatches** vs `mock_cache` on all fields; all 8 builders run |
| 2 | `find_compound_match` now requires **all** of a scenario's concrete bands (floor of 2) instead of a fixed `>= 3`, so low-specificity C20 is reachable | C20 now selected (dist 0) on very-dry indoor reads; differential sweep of 3,780 combos → **201 routing changes, all C20, 0 other routes changed** |
| 3 | Guest path uses `FACTOR_TIEBREAKER`, matching the full-profile path | Tie cases resolve to the same dominant factor on both paths |
| 5 | `/v1/alert` strips `debug` unless `HLHP_DEBUG_RESPONSES=true`; `route()` still computes it so tests are unaffected | Endpoint returns `debug: null` by default, present only with the flag |

**Still open (editorial, not code):**

- **#4 L2 word counts** — decide whether to relax the documented 60–90w target or lengthen the copy.
- **Scenario-tuning note (surfaced during verification):** a Mumbai-monsoon reading resolves to **C13 "Industrial Belt Day"**, not **C06 "Monsoon Acne Trifecta"** — C06 is one band-step further by total distance. This is pre-existing (identical in the original engine) and test-passing (same action/risk cluster), but the alert *narrative* would reference industrial pollution rather than monsoon. Worth an editorial look alongside the C02/C09 items.

*Original audit was review-only; the fixes above were applied afterward at the user's request and re-verified.*
