# SFI Scoring — calibration changes (engine)

Three approved changes, implemented in `hlhp_engine.py` and verified. Originals untouched; the Excel **Bands Reference mirror** still needs the matching edits (listed at the end).

## 1. UV `very_high` (UVI 8–10): 5 → 2 points

Sharper penalty for very-high UV (a top skin stressor) without zeroing it. Chosen over the "→0" option because a 0 sub-score trips the zero-factor override, which would have escalated ~6/8 sunny days and erased the 8–10 vs 11+ distinction.

Updated UV table: low(0–2)=25 · moderate(3–5)=18 · high(6–7)=12 · **very_high(8–10)=2** · extreme(11+)=0.

Effect: very-high-UV days drop ~3 SFI points (e.g. Goa beach noon 47→44, Guard Up→Battle Stations). Note it also lowers UV's score enough to become the **dominant factor** on a small number of very-high-UV readings, so those now serve UV-appropriate cells (a routing improvement, not just an index change).

## 2. Humidity comfortable band: 30–60% → 40–60%

30–39% RH is mildly dry (barrier/TEWL rises below ~40%), so it shouldn't read as "optimal".

Updated humidity table: critical_low(<10)=0 · very_low(10–19)=5 · **low(20–39)=12** · **optimal(40–60)=25** · high(61–79)=12 · very_high(80–89)=5 · extreme(≥90)=0.

Effect: dry 30–39% days lose 13 points (Guard Up→Battle Stations). Because the **band key** for 30–39% flips from `optimal` to `low`, those readings also now pull the "low/dry" humidity cell and match dryness-led compounds more tightly — more accurate guidance, not only a lower number.

## 3. Personal SFI (profile-weighted second index)

New `personal_sfi(points, concern)` + `CONCERN_WEIGHTS`, surfaced as `AlertResponse.personal_sfi`. The **environmental SFI (`score`) is unchanged** and remains the shareable, per-location number. Personal SFI re-weights the *same* four sub-scores by concern (it does not add factors); age/gender stay on the risk axis.

Formula: `personal_sfi = round(100 × Σ(wᵢ·subscoreᵢ) / (25 × Σwᵢ))`.

Starting weights (illustrative — tune clinically):

| Concern | Temp | AQI | UV | Humidity |
|---|---|---|---|---|
| Melasma / Uneven Tone-Tan | 1.0 | 1.0 | 2.0 | 0.5 |
| Acne / Oily Skin | 0.5 | 1.5 | 0.5 | 1.5 |
| Dryness | 1.0 | 0.5 | 0.5 | 2.0 |
| Eczema | 1.0 | 1.0 | 0.5 | 2.0 |

Rationale: pigmentation → UV dominant, with heat/IR-A and pollution (PIH) at 1.0 and humidity minimal; dryness/eczema → humidity leads temperature (water-loss is the primary driver); acne/oily → humidity + pollution lead.

Same day, different friendliness by concern (verified):

| Day | Env SFI | Personal SFI |
|---|---|---|
| Mumbai monsoon | 34 | Acne **27** (humid+polluted hits acne) |
| Goa beach noon (UVI 10) | 44 | Melasma **36** vs Acne **52** |
| Warm-but-dry 20% RH | 52 | Dryness **50** |
| Cold-but-humid 55% RH | 58 | Dryness **69** (humid wins over cold → humidity leads temp) |

## 4. Age & gender — already handled, on the risk axis

Age and gender/life-stage are **already** in the system, as **risk (0–5) modifiers**, not SFI inputs:

- 36 age×concern rules (e.g. Pediatric/Eczema **+2**, Senior/Dryness **+2**, Mature/Melasma **+1**)
- 24 life-stage×concern rules (e.g. Female+Pregnancy/Melasma **+2**, Female+Menopause/Dryness **+2**)

Each adds a clamped risk delta and surfaces an L2 addendum. This is deliberate: age/gender change *vulnerability*, not the environment — so they don't belong in the environmental SFI, and adding them to the Personal SFI as well would double-count what risk already captures. The intended split is three signals:

- **Environmental SFI** (`score`) — place/weather, no person.
- **Personal SFI** (`personal_sfi`) — concern/skin re-weighting (this doc).
- **Risk 0–5** — concern cell + age/gender modifiers (vulnerability).

Future option (not built): if a single "for-this-exact-person" friendliness number is wanted, derive an age/gender adjustment to the Personal SFI from the *same* modifier deltas so it stays consistent and isn't double-counted.

## Verification

- Full suite **402 passed** (392 original + 4 zone + 6 personal SFI).
- Routing blast radius vs pre-change engine: **225/4,320** combos — 198 are RH 30–39% (humidity intent), 27 are very-high-UV dominant-factor flips (UV intent). None outside those regions.
- Backward-compat for zone-awareness preserved; Personal SFI is `None` for guests (no concern).

## Test calibration updates applied (characterization tests of the constants)

- `test_routing_logic.py`: UV `(8, very_high, 5)→2`, `(10, very_high, 5)→2`; humidity `(30, optimal, 25)→(30, low, 12)`.
- `test_canonical_cases.py`: `pune_pre_monsoon` severity now allows `Hostile Mode` (a hot, very-high-UV, dry, hazy pre-monsoon day legitimately scores harsher under the new calibration).

## Excel "Bands Reference" mirror — follow-ups (not yet applied)

The engine is the scoring source of truth; sheet **`2. Bands Reference`** must be updated to match (README: "mirrors live engine"), then re-seeded:

1. UV `Very High (8–10)` points **5 → 2**.
2. Humidity `Low` range **20–29% → 20–39%**; `Optimal` range **30–60% → 40–60%**.
3. Heads-up for editorial: humidity `low` cells now also serve 30–39% — confirm their text doesn't hard-cite "20–29%".
4. Re-seed `band_definitions` after the sheet edit (engine scoring itself doesn't depend on it).

*Engine changes implemented and verified; Bands Reference edits and clinical tuning of the Personal-SFI weights remain as sign-off items.*
