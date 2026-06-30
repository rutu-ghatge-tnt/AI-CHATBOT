# Front-end ↔ v3.3.1 Backend — Compatibility Check

**Question:** can the v3.3.1 handover (the SFI alert engine + library + seeder) power the `hlhp-react` front-end and its 8-screen animated prototype?

**Verdict:** **Compatible as the scoring core, but incomplete as the app backend.** The engine is a clean, well-matched dependency — its outputs map directly onto what the screens display, and the onboarding profile fields are a 1:1 match for the engine's `UserProfile`. But the engine is **stateless and single-shot** ("what's my skin score right now"), while the front-end is a **stateful, longitudinal, engagement-driven** app. Roughly **1 of 8 screens (Hello) is fully served today**, the onboarding profile schema matches, and the engine supplies the *scoring substrate* for ~4 more — but **7 of the 8 endpoints** the front-end README lists are **not** in the handover. They require a new **engagement-service middle tier** (persistence, history, aggregation, pattern-mining, gamification, push) that the engine README explicitly scoped out ("temporal trajectory, forecast, calendar … wrap the engine and need their own tests once built").

This is expected, not a defect — but it means the handover is one of (at least) two backend pieces. The front-end README points to `HLHP_Backend_Architecture_v2.md` for the rest; **that spec is not in the handover**, and it's the missing middle.

---

## What the engine actually exposes (confirmed)

- `POST /v1/alert` — **stateless**. In: `sensors{temperature_c, aqi, uv_index, humidity_pct}`, `profile{skin_type, concern, age_band, gender_state}`, `alert_level{L0|L1|L2}`, `zone`. Out: `score` (env SFI 0–100), `personal_sfi`, `severity_band`, `risk` (0–5), `risk_label`, `confidence`, `alert_text`, `action_cluster`, `cell_source`, `library_version`.
- `GET /v1/health`.
- Storage = the **read-only library** (scenario/guest/compound cells, modifiers, scenarios, zones). **No** user store, log store, or history.

## Screen-by-screen compatibility

| FE screen | README endpoint | Engine coverage | Gap |
|---|---|---|---|
| **Onboarding** | `POST /onboarding/complete` | ✅ **schema match** — the 5 fields are exactly `skin_type, concern, age_band, gender_state` + location→`zone` | needs a **user store** to persist it |
| **Hello / today** | `GET /today` | ✅ **fully derivable** from `/v1/alert` (`score`, `personal_sfi`, `severity_band`, `risk`, `alert_text`, `action_cluster`) | thin adapter + **sensor ingestion** (weather/AQI) + mascot/coach mapping |
| **Log** | `POST /logs` | ⚠️ **partial** — engine can *enrich* a log (compute SFI + bands at that moment) | **log persistence** missing |
| **Streak** | (state) | ❌ missing | streak/day-grid/badge state — pure engagement |
| **Surge** | push | ⚠️ **partial** — per-timepoint SFI is engine-provided | **trajectory monitor** (hourly sample → Δ → threshold) + **push** missing |
| **Recap** | (monthly) | ⚠️ partial — engine computes each day's SFI | **daily history + aggregation** missing |
| **Patterns** | `GET /patterns` | ⚠️ partial — engine gives the per-event bands/SFI that feed it | **pattern-mining over stored logs + env history** missing |
| **Share** | `GET /weekly-card` | ❌ missing | weekly **aggregation over history** |
| **Good day** | `POST /good-day/:id/bottle` | ❌ missing | best-stretch **detection + snapshot store** |

**Tally:** Hello fully served; Onboarding schema-compatible; Surge/Log/Recap/Patterns get their *scoring inputs* from the engine; Streak/Share/Good-day are pure engagement state. The engine is the right dependency for all of them — it just isn't the whole backend.

## Semantic alignment — strong

The data models line up unusually well, which is the important part:

- **SFI 0–100** — the engine's `score` *is* the number the UI shows everywhere (Surge ring "78/100", the 78→54 drop, the weekly card "/100", Recap "Avg SFI 68", Good-day "Avg SFI 78").
- **Personal SFI** — the engine's new `personal_sfi` is a bonus the prototype doesn't use yet: it can drive a per-concern "your skin today" verdict (melasma vs acne see the same day differently).
- **Profile** — onboarding's 5 fields ≈ `UserProfile` + `zone`, exactly.
- **Zones** (HD/HH/CN/TP/CH/TN) — the UI's "Baner · Pune" needs a **city→zone** map (already a flagged productization step) to drive zone-aware matching.
- **Action clusters** (Maintain/Shield/Balance/Hydrate/Calm/Brighten) → the routine guidance / "light routine today" coach line.
- **Alert levels** L0/L1/L2 → compact coach bubble vs L2 explainer.
- **`severity_band`** names → mascot mood + verdict copy (needs a small mapping table).
- **`risk` + `confidence`** → urgency + hedge tone (the engine already appends the "research still emerging" hedge for INFERRED cells inside `alert_text`).

### `GET /today` ← `AlertResponse` (concrete mapping)

| `/today` field | from engine |
|---|---|
| `sfi` | `score` |
| `personal_sfi` | `personal_sfi` |
| `verdict` / band | `severity_band` |
| `risk`, `risk_label` | `risk`, `risk_label` |
| coach line / routine | `alert_text` (L0/L1) + `action_cluster` |
| confidence / hedge | `confidence` (already reflected in `alert_text`) |
| mascot mood | derive from `severity_band` (mapping table) |
| env snapshot | echo input `sensors` (+ `debug.bands_observed` in dev) |

## ⚠️ Recalibration caveat

The prototype's hardcoded numbers (SFI 78→54, 68, etc.) **predate v3.3.1**. Wired live, every number comes from the engine — and after the UV/humidity recalibration the same weather scores differently. **Surge thresholds** (what Δ counts as a "surge") must live in the engagement layer, not be hardcoded in the UI.

## The missing middle: an "Engagement Service"

A stateful app-API that **wraps** the engine (engine stays unchanged):

- **Stores:** `users` (profile + zone), `logs` (symptom event + env snapshot), `daily_sfi` (per-user time-series), `patterns` (mined results), `streak/badges`.
- **Ingestion:** city/GPS → weather + AQI → `SensorReading`; city → `zone`.
- **Services:** `/today` (sensors → `/v1/alert` → UI shape); log write+enrich; **surge monitor** (hourly SFI sample → Δ over window → FCM push); **daily-SFI writer** (cron); **pattern miner** (batch correlate logs vs env); **aggregation** (weekly-card / recap / good-day); **gamification** (streak/badge rules).
- These contracts are what `HLHP_Backend_Architecture_v2.md` is meant to define — **obtain or write that spec**; it's the gap between this engine and the front-end.

## Recommended bridge sequence (engine untouched, all additive)

1. **App-API gateway + `/today`** (pure adapter over `/v1/alert`) → unblocks **Hello + Onboarding** immediately.
2. **`users` + `logs` stores** → **Log + Streak**.
3. **`daily_sfi` writer** (cron calling the engine per user/zone) → **Recap + Share + Good-day** aggregation.
4. **Surge monitor + push** → **Surge**.
5. **Pattern miner** → **Patterns**.

## Bottom line

The v3.3.1 handover is a **solid, well-aligned scoring core** for this front-end — clean API, matching profile schema, and an SFI vocabulary the UI already speaks (plus Personal SFI as upside). It is **not, by itself, the app backend**: the engaging, longitudinal experience needs an engagement-service tier built around it. Nothing in the engine blocks that; it's additive. The one true unknown is `HLHP_Backend_Architecture_v2.md` — locate it (or let me draft it from this analysis) and the path to wiring the prototype to live data is clear.
