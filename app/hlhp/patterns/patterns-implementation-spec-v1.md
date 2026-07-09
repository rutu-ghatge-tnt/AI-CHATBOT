# Patterns Tab — Developer Implementation Spec v1.0

**Product:** SkinBB HLHP · **Feature:** Patterns tab (unlock, detection, decay, AI narration)
**Companion doc:** `patterns-tab-rules-v1.md` (product rationale + scenarios). This doc is the build contract.
**Date:** 7 Jul 2026 · **Decisions signed off by:** Ajit

---

## 1. Scope

- Unlock state machine (LOCKED → EARLY_SIGNALS → UNLOCKED; post-unlock ACTIVE / FADING / PAUSED)
- Deterministic pattern-detection engine (no AI in detection)
- AI narration layer (generation, validation, caching, fallback)
- Lifecycle prompts & notifications with rate limits
- Data model + API surface + acceptance tests

Out of scope v1: AM/PM dual logging, forecast personalisation gates, photo timeline.

---

## 2. Configuration constants

```
WINDOW_DAYS              = 30      # rolling window length
UNLOCK_HARD_FLOOR_DAYS   = 30      # min days since FIRST LOG, non-negotiable
UNLOCK_LOG_DAYS          = 25      # log-days required within any rolling window
EXPOSURE_MIN_DAYS        = 5       # adverse-driver days with logs, any driver combined
PROMOTE_MIN_EXPOSURE     = 5       # per-pattern E to display
PROMOTE_MIN_LIFT         = 1.5
DEMOTE_LIFT              = 1.2     # sustained 14 days → demote to Emerging
LABEL_HIGH               = E>=10 AND lift>=2.0
LABEL_MODERATE           = E>=7  AND lift>=1.5
ACTIVE_MIN_LOG_DAYS      = 20      # in rolling window
FADING_MIN_LOG_DAYS      = 12
REACTIVATION_RULE        = 3 log-days within 5 calendar days
MAX_DISPLAYED_PATTERNS   = 3       # rest under "Emerging"
BASELINE_FLOOR           = 0.05    # denominator floor for lift
SYMPTOM_LAG_HOURS        = 24
NARRATION_REFRESH        = weekly (Sun 02:00 local) + on unlock + on pattern promote/demote
```

All constants server-side config, not hardcoded in clients.

## 3. Definitions

- **Log-day:** calendar day (user's local timezone) with ≥1 saved log. Multiple logs same day = 1 log-day (richness is stored, gates unaffected).
- **first_log_date:** date of the user's first ever saved log. The 30-day floor counts from here, **not** signup.
- **Adverse day (driver D):** day where D's band (per v3.5 band tables, city-resolved) is in the adverse set for that driver.
- **Exposure E(D):** adverse-D days in window having a log on the same day or the next day (lag capture).
- **Hit H(D,S):** exposure day where symptom S was logged within `SYMPTOM_LAG_HOURS`.
- **Baseline B(S):** rate of S across calm (non-adverse, any driver) logged days in window; floor at `BASELINE_FLOOR`.

## 4. State machine

States: `LOCKED`, `EARLY_SIGNALS`, `UNLOCKED_ACTIVE`, `UNLOCKED_FADING`, `UNLOCKED_PAUSED`. Persisted per user in `pattern_state`. Evaluate on: (a) every log save, (b) daily job at local midnight.

```
evaluate(user, today):
  d_since_first = daysBetween(user.first_log_date, today)
  win           = logs in [today-29, today]
  logDays       = distinctDays(win)
  exposureDays  = distinct days in win that are adverse(any driver) AND logged

  if not user.unlocked:
      if d_since_first >= 30 AND logDays >= 25 AND exposureDays >= 5:
          user.unlocked = true; fire(UNLOCK)            # one-time, irreversible
          state = UNLOCKED_ACTIVE
      elif d_since_first >= 30 AND logDays >= 25:       # exposure gate pending
          show STABILITY_PARTIAL (stability pattern + "calm month" copy)
          state = EARLY_SIGNALS
      elif logDays >= 5:  state = EARLY_SIGNALS
      else:               state = LOCKED
  else:
      if   logDays >= 20: state = UNLOCKED_ACTIVE
      elif logDays >= 12: state = UNLOCKED_FADING
      else:               state = UNLOCKED_PAUSED
```

Rules:
- `unlocked` is a **one-way flag**. Decay states never re-lock.
- UNLOCK event fires exactly once; dedupe by flag.
- FADING and PAUSED entry each fire **max one** push per episode (track `last_decay_notified_state`).
- Reactivation: while PAUSED, if 3 log-days occur within any 5-day span → re-evaluate (will land ACTIVE or FADING); fire REACTIVATED event.
- Projected unlock date (for meter copy): `today + max(0, 30 - d_since_first, 25 - logDays)` naive estimate assuming daily logging; recompute daily.

## 5. Detection engine (deterministic — runs server-side, daily + on log save)

```
detect(user, today):
  win = window data (logs, env bands per day, city tags)
  candidates = []
  for D in [TEMP, UV, HUMIDITY, AQI]:
      exp = exposureDays(D, win)                # per §3, per city (see 5.1)
      if len(exp) == 0: continue
      for S in SYMPTOMS:                        # dry, oily, dull, breakout, spots
          hits  = [d for d in exp if S logged within 24h of d]
          match = len(hits)/len(exp)
          lift  = match / max(baseline(S, win), 0.05)
          candidates.append({D, band, S, E:len(exp), H:len(hits), match, lift,
                             lag:medianLagHours, zones:topZones(S, hits),
                             weekdaySplit, library_cell: lookupCell(D, band, user.skin, user.concern)})
  promoted = [c for c in candidates if c.E >= 5 and c.lift >= 1.5]
  label each promoted per LABEL_* rules; sort by (label, match); display top 3, rest = Emerging
  demote any previously-promoted pattern whose lift < 1.2 for 14 consecutive days → Emerging
  persist to `patterns` table with full inputs (auditability)
```

### 5.1 Sub-rules
- **City handling:** logs are tagged with that day's resolved city. Exposure/patterns computed per city; a city needs ≥5 logged days in-window to contribute patterns. Log-day *counting* for gates is city-agnostic.
- **Profile change:** on skin/concern change, set `patterns.recalibrating_until = today+7`, recompute with new library cells; never delete history.
- **Backdated logs:** allowed up to 48h back; older edits rejected (protects window math).
- **Timezone:** all day boundaries in the user's current device timezone, captured per log.
- **"Normal" logs:** count fully as log-days; feed the Stability/resilience pattern (E = adverse days, H = adverse days with NO symptom logged; same math inverted).

## 6. Data model (new/changed)

```
daily_logs(user_id, log_date, city, symptoms[], zones[], created_at, tz)
              UNIQUE(user_id, log_date)          # richness merged into one row/day
env_daily(city, date, temp_band, uv_band, hum_band, aqi_band, raw values)
pattern_state(user_id, state, unlocked_at, first_log_date,
              log_days_30, exposure_days_30, projected_unlock_date,
              last_decay_notified_state, updated_at)
patterns(id, user_id, driver, band, symptom, city, E, H, match, lift, label,
         status[promoted|emerging|demoted|recalibrating], lag_hours,
         zones[], weekday_hits, weekend_hits, library_cell_id, pmids[],
         first_detected, last_confirmed, inputs_snapshot JSON)
narration_cache(user_id, kind[pattern|unlock|weekly_digest], pattern_id?,
                text, model, input_packet JSON, generated_at, valid)
```

API (respecting existing split — engine vs engagement):
- `GET /v1/patterns/state` → pattern_state + meter numbers
- `GET /v1/patterns` → promoted + emerging with stats
- `POST /v1/logs` (existing) → triggers evaluate() + detect()
- `GET /v2/patterns/narration` → cached narration texts
- `POST /v2/patterns/reactivation-progress` → 3-of-5 challenge status

## 7. AI narration contract (AI narrates; it never detects)

**When:** on UNLOCK, weekly batch, on promote/demote. **Never** on tab open (serve cache only).

**Request packet (only computed data — never raw logs, never PII):**
```json
{
  "voice_rules": "<copy-bank voice constraints>",
  "profile": {"skin":"oily","concern":"acne","age_band":"Adult","life_stage":"Female"},
  "city": "Pune",
  "patterns": [{
      "driver":"humidity","band":"High","symptom":"breakout",
      "E":12,"H":10,"match":0.83,"lag_hours":24,
      "zones":["cheeks"],"weekday_hits":8,"weekend_hits":2,
      "label":"HIGH","library_l1":"<cell text>","pmids":["31284694"]}],
  "month_summary": {"log_days":26,"surges":[{"date":"2026-06-12","driver":"temp","symptom_logged":true},
                                            {"date":"2026-06-24","driver":"temp","symptom_logged":false}]},
  "outputs_wanted": ["pattern_narrative","unlock_headline","weekly_digest"]
}
```

**Response schema:** JSON with one text field per requested output, ≤ 480 chars each.

**Validation (blocking, server-side):**
1. Every numeral in output must appear in the input packet (allow derived forms: "10 of 12", "83%"). Fail → regenerate once → fallback.
2. No product recommendations, no medical claims beyond library L1/L2 text.
3. Voice lint: banned-phrase list from Copy Bank "Voice & Rules" sheet.

**Fallback:** deterministic template per pattern ("{Driver} {band} days matched your {symptom} logs {H} of {E} times — strongest on your {zone}."). The screen must render fully with AI unavailable.

**Privacy:** user_id replaced by request-scoped token; no name, email, precise location (city only) in the packet.

## 8. Prompts & notifications

Copy matrix lives in `patterns-tab-rules-v1.md` §6 (5 lifecycle states × surfaces, with `{n}`, `{projected_date}` variables). Implementation rules:

| Event | Channel | Rate limit |
|---|---|---|
| Day-2 encouragement | push | once ever |
| On-track weekly ("one week to patterns") | push | 1/week, only if logDays pace ≥ target |
| Behind-pace nudge (state C) | push | **max 1/week** |
| UNLOCK | push + in-app full-screen | once ever |
| Weekly digest (post-unlock) | push | 1/week, only in ACTIVE |
| FADING entered | push | 1/episode |
| PAUSED entered (reactivation challenge) | push | 1/episode |

All in-app meters recompute from `/v1/patterns/state` — clients never compute gate math locally.

## 9. Analytics events (instrument all)

`pattern_meter_viewed`, `pattern_state_changed{from,to}`, `pattern_unlocked{d_since_first, log_days}`, `pattern_card_viewed{pattern_id}`, `reactivation_started/completed`, `narration_served{kind, fallback:bool}`, `unlock_push_opened`. Funnel of record: first_log → 5 logs → 15 logs → 25/30 met → unlocked → ACTIVE at day 60.

## 10. Acceptance criteria (given / when / then)

1. Given first_log_date = D0 and user logs daily, when day D0+24 ends with 25 log-days, then state ≠ UNLOCKED (hard floor); when D0+29 ends (day 30), then UNLOCKED fires once and `unlocked_at` set.
2. Given 24 log-days in window on day 35, when user logs today, then UNLOCKED fires today (rolling window, delayed unlock).
3. Given 25 log-days but 3 exposure days, then state = EARLY_SIGNALS with STABILITY_PARTIAL flag; when exposure reaches 5, then full UNLOCK fires without further user action.
4. Given 10 logs saved on one calendar day, then log_days increments by exactly 1.
5. Given an unlocked user with 15 log-days in window, then state = UNLOCKED_FADING and exactly one FADING push per episode.
6. Given PAUSED user logging on days 1,3,5 of any 5-day span, then REACTIVATED fires and state recomputes.
7. Given E=4 for a candidate with lift 3.0, then it is NOT displayed (small-sample guard).
8. Given a promoted pattern whose lift stays <1.2 for 14 days, then status → demoted and demotion copy shows.
9. Given narration output containing a numeral absent from the input packet, then it is rejected and the template fallback is served (`narration_served{fallback:true}`).
10. Given AI provider down, when Patterns tab opens, then screen renders fully from cache/templates (no spinner block).
11. Given a skin-type change, then patterns show "Recalibrating" ≤7 days and history rows persist.
12. Given user changes timezone, then existing log_days are not recounted (day boundaries stamped at write time).

## 11. Build order (suggested)

1. `env_daily` banding + `daily_logs` unique-day model
2. Gate evaluation + state machine + meter endpoint
3. Detection engine + patterns persistence
4. Lifecycle prompts + notifications with rate limits
5. AI narration service (packet builder → LLM → validator → cache) + fallback templates
6. Unlock celebration + decay/reactivation UI states
