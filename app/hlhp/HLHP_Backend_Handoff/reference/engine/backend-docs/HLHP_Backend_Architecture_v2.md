# HLHP Backend Architecture v2 — Engagement Service

The front-end README referenced an `HLHP_Backend_Architecture_v2.md` that didn't exist. This is it, written to match the **reference implementation** now shipped in `engagement_service/`.

## Two tiers, one engine

```
            ┌──────────────────────────── Front-end (React, 8 screens) ───────────────────────────┐
            │  Hello   Log   Streak   Surge   Recap   Patterns   Share   Good-day                   │
            └───────────────────────────────────────┬──────────────────────────────────────────────┘
                                                     │  HTTPS  (/v2/*)
            ┌────────────────────────────── Engagement Service (this tier) ───────────────────────┐
            │  stateful: profiles · logs · daily SFI history · streaks · surge monitor ·           │
            │            pattern miner · weekly/monthly aggregation · /today adapter               │
            └───────────────────────────────────────┬──────────────────────────────────────────────┘
                                                     │  in-process call: route(sensors, profile, zone)
            ┌──────────────────────────────── SFI Alert Engine (v3.3.1) ──────────────────────────┐
            │  stateless: classify → SFI/personal SFI → severity → compound/zone match → alert     │
            │  library: 1,380 cells + 21 scenarios + modifiers + zones (Mongo/Redis in prod)       │
            └──────────────────────────────────────────────────────────────────────────────────────┘
```

**Design rule:** the engine stays stateless and unchanged; the engagement tier owns all state, time, and gamification. Everything is additive around the engine.

## Data model (engagement tier)

| Store | Key | Fields |
|---|---|---|
| `users` | user_id | skin_type, concern, age_band, gender_state, city, **zone**, created_at |
| `logs` | user_id → [] | ts, date, symptom, location, count, **sfi**, action_cluster, humidity/uv/aqi/temp bands |
| `daily_sfi` | user_id → {date} | date, sfi, personal_sfi, band |
| `patterns` | user_id → [] | (derived) symptom, driver, match_pct, n |
| `gamification` | user_id | streak, earned_badges |

`users` rows map 1:1 to the engine's `UserProfile` + `zone`. `logs`/`daily_sfi` are the time-series the engine never keeps.

## Endpoint contracts

All under `/v2`. Full request/response shapes are in `engagement_service/engagement_api.py`; summary:

| Endpoint | Screen | Notes |
|---|---|---|
| `POST /onboarding/complete` | Onboarding | body = 5 profile fields + city; resolves city→zone |
| `GET /today?user_id` | Hello | engine `AlertResponse` → `{sfi, personal_sfi, band, mascot_mood, coach_line, action_cluster, risk, ...}`; writes today's SFI to history |
| `POST /logs` | Log | enriches each log with live SFI + observed bands |
| `GET /streak?user_id` | Streak | consecutive active days + badge state |
| `GET /patterns?user_id` | Patterns | needs ≥5 logs; mines symptom↔humidity co-occurrence |
| `GET /weekly-card?user_id` | Share | 7-day avg + trend vs prior week |
| `GET /recap?user_id&days` | Recap | N-day series + surge-day count |
| `GET /surge/check?user_id` | Surge | live SFI vs rolling baseline → push payload when drop ≥ threshold |
| `GET /good-day?user_id` + `POST /good-day/bottle` | Good-day | best-stretch detection + save |

### `/today` field mapping (the core adapter)

`sfi←score · personal_sfi←personal_sfi · band/verdict←severity_band · risk,risk_label←risk,risk_label · coach_line←alert_text · action_cluster←action_cluster · confidence←confidence · mascot_mood←map(severity_band)`.

## Services

- **Today adapter** — fetch sensors for the user's zone → `route()` → map to UI shape; append to `daily_sfi`.
- **Surge monitor** — a cron/worker calls `route()` hourly per active user; if SFI drops ≥ threshold vs the 7-day baseline, emit a push. (`/surge/check` is the synchronous form.)
- **Daily-SFI writer** — once/day per user, persist the day's score (powers Recap, Share, Good-day).
- **Pattern miner** — batch job correlating logs against their stored environment bands (reference: symptom × high-humidity; production: extend to UV/AQI/sleep, significance testing).
- **Aggregation** — weekly/monthly rollups from `daily_sfi` + `logs`.
- **Gamification** — streak counter + badge rules (first log, 7/30-day, survived-surge, first-pattern).

## Engine integration

The engagement tier imports the engine as a library and calls `route(SensorReading, UserProfile, level, cache, zone=...)` directly (in-process — no HTTP hop). The engine's `motor`/`redis` imports are lazy, so the tier (and tests) run without DB drivers when using `MockLibraryCache`. In production, construct the engine's `LibraryCache` (Mongo+Redis) once and pass it to `route()`.

## Reference vs production

| Concern | Reference (shipped) | Production |
|---|---|---|
| Scoring cache | `MockLibraryCache` (Excel) | `LibraryCache` (Mongo+Redis) |
| Stores | in-memory dicts | MongoDB collections |
| Sensors | per-zone mock | live weather + AQI API |
| City→zone | ~35-city subset | library's 62-city map (sheet 1) |
| Auth / push | none | JWT/Firebase + FCM |
| Pattern miner | humidity co-occurrence | multi-factor + significance |

## Build sequence (recommended)

1. `/today` adapter + onboarding (unblocks Hello + Onboarding) — **done in the reference.**
2. `users` + `logs` stores → Log + Streak — **done (in-memory).**
3. `daily_sfi` writer → Recap + Share + Good-day — **done (in-memory).**
4. Surge monitor + push transport — `/surge/check` **done**; wire FCM in prod.
5. Pattern miner — reference miner **done**; enrich for prod.

## Status

The reference implementation in `engagement_service/` covers all 8 screens' data needs end-to-end (9 passing tests, scoring via the real v3.3.1 engine). Production-hardening = swap the four reference components above and add auth/push. No engine changes required.
