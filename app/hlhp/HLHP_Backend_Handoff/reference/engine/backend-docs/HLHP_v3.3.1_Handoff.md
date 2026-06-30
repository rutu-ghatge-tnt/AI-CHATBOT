# SkinBB HLHP — Change Summary & v3.3.1 Handoff

**Bottom line:** **v3.3.1 is built and verified end-to-end — 402 tests passing.** The approved library edits (C06, C21, Bands Reference mirror) and the SFI recalibration are all applied in `SkinBB_HLHP_Scenario_Library_v3_3_1.xlsx`, and the (fixed) seeder ingests it cleanly. Remaining items are operational — run the seeder against live MongoDB and wire the zone input — plus optional polish.

---

## Status at a glance

| Area | Change | Type | Status |
|---|---|---|---|
| Seeder | Fixed `build_scenario_cells` column mapping (was crashing) | code | ✅ done & verified |
| Engine | Guest dominant-factor tiebreaker aligned to full-profile | code | ✅ done |
| Engine | `debug` payload gated out of prod responses | code | ✅ done |
| Engine | C20 made reachable (adaptive band requirement) | code | ✅ done & verified |
| Engine | Zone-aware compound matching (opt-in) | code | ✅ done; needs zone wired by app |
| SFI | UV `very_high` 5 → 2 (+ Bands Reference mirror) | code+library | ✅ in v3.3.1 |
| SFI | Humidity comfortable band 40–60% (+ mirror) | code+library | ✅ in v3.3.1 |
| SFI | Personal SFI (profile-weighted) + tuned weights | code | ✅ done (clinical re-tune optional) |
| Library | C06 Temp `hot → warm` | library | ✅ in v3.3.1 |
| Library | C21 `+Temperature` driver | library | ✅ in v3.3.1 |

---

## Engine changelog (`hlhp_engine.py`, except where noted)

1. **Seeder fix** (`seed_library_to_mongo.py`) — removed the phantom `points` column; single-factor seeding now produces 750 docs with 0 mismatches vs `mock_cache`.
2. **Guest tiebreaker** — guest path uses `FACTOR_TIEBREAKER`, so guests and logged-in users resolve identical weather the same way.
3. **Debug gating** — `/v1/alert` strips `debug` unless `HLHP_DEBUG_RESPONSES=true`; `route()` still computes it for tests.
4. **C20 reachability** — `find_compound_match` requires *all* of a scenario's concrete bands (floor 2) instead of a fixed ≥3; only C20 newly activates, 0 other routes changed.
5. **Zone-aware matching** — optional `zone` on `AlertRequest`; prefer in-zone scenarios, fall back to all; unknown codes ignored. Backward-compatible (0 diffs when zone omitted).
6. **UV recalibration** — `very_high` (8–10) now 2 pts (was 5).
7. **Humidity recalibration** — comfortable band 40–60%; 30–39% now scores `low` (and routes to dry-skin cells).
8. **Personal SFI** — `personal_sfi()` + `CONCERN_WEIGHTS`, surfaced as `AlertResponse.personal_sfi`; environmental `score` unchanged. Age/gender stay on the risk axis.

## Tests — 402 passing

Original 392 + 4 zone-aware + 6 Personal-SFI. Calibration test expectations updated to the new constants: UV `(8/10)→2`, humidity `(30)→low/12`, canonical `pune_pre_monsoon`→ allows `Hostile Mode`. (Sandbox runs stub `motor`/`redis` only — production code untouched.)

## Deliverable files (this folder)

| File | What it is |
|---|---|
| `hlhp_engine.py` | Patched engine (all 8 changes above) |
| `seed_library_to_mongo.py` | Fixed seeder |
| `test_zone_aware.py`, `test_personal_sfi.py` | New test suites |
| `HLHP_v3.3_Audit.md` | Original full audit + fixes applied |
| `HLHP_v3.3_Scenario_Change_Spec.md` | C06/C21 sign-off spec |
| `HLHP_ZoneAware_Matching.md` | Zone-aware design + verification |
| `HLHP_SFI_Calibration.md` | UV/humidity/Personal-SFI calibration + age/gender note |
| `HLHP_v3.3.1_Handoff.md` | This document |

---

## v3.3.1 — applied & verified

Built into `SkinBB_HLHP_Scenario_Library_v3_3_1.xlsx`:

1. **C06** Temp `hot → warm` · **C21** `+Temperature` driver (sheet 8).
2. **Bands Reference mirror** (sheet 2): UV `Very High` 5→2; Humidity `Low` 20–39%, `Optimal` 40–60%.
3. README version note bumped. *(Optional C06 UV→high deliberately not applied — left for clinical review.)*

Verification, all against v3.3.1:

- Seeder ingests cleanly — 750 / 630 / 230 / 21 / 36 / 24 / 6 / 25 docs; edits flow through (C06 bands temp=warm, C21 drivers include Temperature, band_definitions UV very_high=2, humidity ranges 20–39 / 40–60).
- Full suite **402 passed**.
- Behaviour: Mumbai monsoon now → **C06** even without a zone (action Balance, risk 5); C20 and C21 both reachable; zone-aware matching + Personal SFI intact.
- Test expectations updated for the recalibration: `test_routing_logic` (UV 8/10→2, humidity 30→low/12), `test_canonical_cases` (pune allows Hostile Mode), `test_zone_aware` (re-routing demo moved to a C08→C07 coastal case, since C06 is now fixed at the library level).

## Remaining (operational / optional)

- **Run the seeder against live MongoDB** in your environment: `python seed_library_to_mongo.py --xlsx SkinBB_HLHP_Scenario_Library_v3_3_1.xlsx --version 1.0.1` (verified here at the document-build level; needs your DB to actually write + index).
- **Wire the zone input** — map user city/GPS → zone code into `AlertRequest.zone` to activate zone-aware matching (safe no-op until then).
- **Optional:** clinical re-tune of `CONCERN_WEIGHTS`; L2 word-count spec; band-cliff smoothing; C06 UV→high.
- Set `HLHP_DEBUG_RESPONSES` only in dev.
