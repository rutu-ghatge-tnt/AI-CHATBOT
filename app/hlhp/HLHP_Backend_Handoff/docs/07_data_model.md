# 07 — Data Model

Three runtime stores + the read-only evidence library. The reference uses
in-memory dicts (`USERS / LOGS / DAILY`); production swaps each for a collection.

> Reference: `reference/engine/engagement_service/engagement_api.py` (stores),
> `reference/engine/seed_library_to_mongo.py` (library seeding).

---

## Runtime stores

### `users`  (profile)
```json
{
  "user_id": "…",
  "skin_type": "Combination",          // Normal/Dry/Oily/Combination/Sensitive
  "concern": "Acne",                   // one of 14
  "life_stage": "Female + Menstrual Cycle",  // gender state (see library sheet 13)
  "age_band": "…",
  "city": "Pune",
  "zone": "TP",                        // resolved from city_zone
  "created_at": "…"
}
```

### `logs`  (append-only symptom events) — see doc 02
```json
{ "user_id","ts","date","symptoms":[],"areas":[],"sfi",
  "action_cluster","temp_band","uv_band","aqi_band","humidity_band" }
```
Index: `(user_id, date)`. The snapshotted bands are what Patterns mines.

### `daily_sfi`  (per-user time series) — see docs 03/04
```json
{ "user_id","date":"YYYY-MM-DD","sfi","personal_sfi","band","driver" }
```
Index: `(user_id, date)` unique (upsert per day). Written on check-in, on log,
and by the daily cron. This is the backbone of Streak, Recap and Share.

> Use **local date** as the key everywhere (`date`), not UTC, so day boundaries
> match the user's experience.

---

## Read-only evidence library

Seeded from `SkinBB_HLHP_Scenario_Library_v3_5.xlsx` (in `reference/evidence/`).
The UI consumes a JSON export (`hlhp-evidence.json`) produced by
`export_evidence.py`; the engine reads the same data from Mongo/Redis. Tables the
scoring needs:

| Export key | Source sheet | Used by | Shape |
|---|---|---|---|
| `bands` | 2. Bands Reference | SFI (doc 01) | per factor: `[{label, range, points(0–25), key}]` |
| `master` | 10. Master Library | Hello alert (doc 01 §6) | `factor\|band_key\|skin\|concern → {risk, confidence, l0, l1, l2, action, zones, pmids, evidence}` (1,140 cells) |
| `compound_cells` | 9. Compound Cell Library | named-scenario alerts | `scenario\|skin\|concern → {…}` (940 cells) |
| `compounds` | 8. Compound Scenarios Index | scenario detection | 21 named multi-factor scenarios w/ band tuples |
| `zones`, `zone_weather`, `city_zone` | 1. India Climatic Zones | city→zone→weather | 6 zones, 46 cities |
| `nuggets` | 16. Did-You-Know | Learn (doc 06) | 41 cited cards keyed by factor |
| `gender_states`, `gender_rules` | 13. Gender + Life-Stage | SFI delta (doc 01 §8) | 9 states; 40 `state\|concern → {risk_delta, action, addendum, anchor}` |
| `time_overlay` | Time Overlay | time window (doc 01 §9) | 25 `factor\|band_key → {morning, evening}` |
| `nutrition`, `lifestyle` | 14/15 Modifiers | (future) | cited nudges |

Counts (v3.5): **1,140** master · **940** compound · **14** concerns · **5** skins ·
**41** nuggets · **9** life-stages · **40** gender rules · **25** time overlays.

### Regenerating the export

```bash
python3 reference/evidence/export_evidence.py \
  reference/evidence/SkinBB_HLHP_Scenario_Library_v3_5.xlsx  out.json
```
The script is **schema-stable across v3.4→v3.5** — adding cells/concerns/nuggets
needs no code change. If a *sheet name or column* changes, update the parser
(it reads sheets by name; column order within a sheet is positional).

---

## Locked product rules (enforce in any generated/served copy)

- SFI always capitalised; first mention "Skin Friendliness Index (SFI)".
- Mode/band names are proper nouns: Paradise Mode → Smooth Sailing → Guard Up →
  Battle Stations → Hostile Mode → Code Red.
- No product or brand names (category labels only).
- The word **"advice" is banned** — use "information"/"education".
- User-facing text is **zone-phrased, not city-named** (v3.5 fix); city names live
  only in internal metadata + the `city_zone` map.
