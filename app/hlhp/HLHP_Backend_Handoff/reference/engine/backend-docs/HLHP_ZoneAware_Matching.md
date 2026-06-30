# Zone-Aware Compound Matching — design + verification

**Problem.** The compound matcher scored scenarios on weather bands + dominant driver only — it never read the `zones` column, and the engine had no location input. So an **inland** scenario (C13 "Industrial Belt Day", zones CN/HD/TP) could win a **coastal** reading (Mumbai monsoon) purely because its bands sat one step closer than the coastal C06. That's why an industrial-pollution alert surfaced for a monsoon day.

**Fix (prototype).** Make matching zone-aware, fully opt-in.

## What changed (engine only — `hlhp_engine.py`)

- `AlertRequest` gains an optional `zone` field (e.g. `HH`, `CN`, `HD`, `TP`, `CH`, `TN`).
- `route(..., zone=None)` threads it through; `/v1/alert` passes `req.zone`.
- `find_compound_match(..., zone=None)` now runs **two passes** when a zone is given:
  1. **In-zone pass** — only scenarios whose `zones` include the user's zone (or are zone-agnostic `"any"`).
  2. **Fallback pass** — the full set, used only if nothing in-zone matched (so the engine never goes silent).
  When `zone` is `None`, it's a single legacy pass — behaviour is unchanged.
- **Unknown-code guard:** a zone not present in the library is ignored (treated as `None`), so a typo can't suppress all matches.
- `debug.zone` records the (validated) zone used.

The `zones` data already exists on every scenario and cell; this only starts *using* it.

## Behaviour contract

| Input | Behaviour |
|---|---|
| `zone=None` (default) | Legacy: zone never consulted |
| `zone` recognised | Prefer in-zone scenarios; fall back to global best if none fit |
| `zone` unrecognised | Ignored (== `None`) |

## Zone codes (from sheet 1)

`HD` Hot & Dry · `HH` Warm & Humid Coastal · `CN` Composite North Plains · `TP` Temperate Plateau · `CH` Cold Himalayan · `TN` Tropical Northeast

## Verification (against the **original** v3.3 library — no library edits)

| Check | Result |
|---|---|
| Full suite (no zone passed) | **392 passed** (unchanged) |
| New `test_zone_aware.py` | **4 passed** → suite now **396** |
| Backward compatibility: `route(zone=None)` vs pre-zone engine, 3,780 combos | **0 differences** |
| Mumbai monsoon, `zone="HH"` | **C13 → C06** (coastal Monsoon Acne Trifecta) — fixed *without* touching C06 |
| Mumbai monsoon, `zone="XX"` (bogus) | C13 (ignored, == no zone) |
| Delhi smog, `zone="TN"` (no TN scenario fits) | Falls back → C10, still alerts |
| Effect of `zone="HH"` on warm/humid grid, 432 combos | 57 routes change, **all out-of-zone → in-zone**: C13→C06 (33), C08→C07 (21), C08→C04 (3) |

Every routing change is an out-of-zone scenario being replaced by an in-zone one; nothing moved in an unrelated direction.

## Relationship to the earlier C06 / C21 spec

- **C06 `hot → warm`** is now **optional**. Zone-awareness fixes the Mumbai misroute on its own (C13 is filtered out for a coastal user). The `hot` band is still arguably a definition error worth correcting, but it's no longer required to resolve the "Industrial Belt Day" confusion.
- **C21 `+Temperature` driver** is **independent** and still recommended — it's an internal-consistency fix unrelated to zones.

## To productionise

1. **Supply the zone.** The app already knows the user's location (the weather sensors come from it); map city/GPS → zone code and pass it in `AlertRequest.zone`. Until then, omitting it is safe (legacy behaviour).
2. Re-seed not required — no library change. (If C06/C21 edits are later approved, those need a re-seed.)
3. Consider persisting the user's home zone on `UserProfile` for cases where only profile context is available.

*Prototype implemented on the working engine copy in this folder; original uploads untouched. No library files were modified.*
