# 02 — Log Screen

**Purpose:** let the user record how their skin feels today, enriched with the
live environmental snapshot, and persist it as the raw event stream that Streak,
Recap and Patterns are all built from.

> Reference: `POST /v2/logs` in `reference/engine/engagement_service/engagement_api.py`;
> UI behaviour in `reference/ui-logic/` + the `LogScreen` component.

---

## What the user captures (UI)

- **Symptom chips — multi-select:** `Dry · Oily · Dull · Breakout · Spots`
  (the 5 v3.5 user-facing options). "Spots" exists because acne often leaves
  marks behind.
- **Face areas — multi-select, only for `Breakout` / `Spots`:**
  `Full face · Forehead · Cheeks · Chin · Nose · Jaw`. ("Full face" is mutually
  exclusive with the specific areas.) Other symptoms skip this step.
- **Save** commits the whole day's log in one action.

The captured panel also shows the **environment line** for the day (the dominant
driver / surge), which comes from the same scan that powers Hello.

---

## What gets stored (one log event)

The reference backend stores this per `POST /v2/logs` (extend with `areas`):

```json
{
  "ts": "2026-06-30T08:14:00Z",     // event timestamp (UTC)
  "date": "2026-06-30",             // local date (the streak/series key)
  "user_id": "…",
  "symptoms": ["breakout","spots"], // multi-select (reference stores single `symptom`)
  "areas": ["forehead","cheeks"],   // only when breakout/spots; [] otherwise
  "sfi": 67,                         // SFI at the moment of logging (enrich on write)
  "action_cluster": "Balance",
  "humidity_band": "Optimal",        // the 4 bands at log time — feeds Patterns
  "uv_band": "High",
  "aqi_band": "Satisfactory",
  "temp_band": "Warm"
}
```

> **Why store the bands on the log:** Patterns mines symptom ↔ environment
> co-occurrence. Snapshotting the bands at write-time means you never have to
> re-derive historical weather. This is the key design decision of the Log
> screen — keep it.

A log write also **upserts today's daily SFI** (see `daily_sfi`, doc 07) so the
day counts toward the streak and appears in Recap.

---

## Write path (pseudocode)

```python
def add_log(user_id, symptoms, areas):
    u = get_user(user_id)                       # 404 if no profile
    weather = live_weather(u.zone_or_gps)
    scan = compute_today(u, weather, now())     # doc 01 — gives SFI + bands
    log = {
        "ts": utcnow(), "date": local_date(), "user_id": user_id,
        "symptoms": symptoms, "areas": areas if needs_area(symptoms) else [],
        "sfi": scan.sfi, "action_cluster": scan.action_cluster,
        **{f"{f.lower()}_band": scan.bands[f] for f in BANDS},
    }
    LOGS.insert(log)
    DAILY.upsert(user_id, local_date(), sfi=scan.sfi,
                 personal_sfi=scan.personal_sfi, band=scan.mode)
    return {"logged": log, "streak": streak(user_id)}
```

`needs_area(symptoms)` = `True` if `symptoms ∩ {breakout, spots}` is non-empty.

---

## Endpoint contract

`POST /v2/logs`

Request:
```json
{ "user_id": "…", "symptoms": ["breakout"], "areas": ["forehead"] }
```
Response:
```json
{ "logged": { …the stored log… }, "streak": 24 }
```

> The reference `engagement_api.py` currently accepts a single `symptom` +
> `location` + `count`. The v3.5 UI is multi-select with `symptoms[]` + `areas[]`.
> Adopt the array shape; keep one event per save (not one per symptom) so the
> day counts once toward the streak.

---

## Edge cases

- **No symptoms selected** → Save is disabled; no write.
- **Multiple saves same day** → upsert the daily SFI (idempotent per date); the
  log events themselves are append-only (a user may log twice; that's fine, but
  the streak counts the *date* once — see doc 03).
- **No profile** → 404 ("complete onboarding first").
- **"Full face" + specific area** → "Full face" wins (clear the specifics).
