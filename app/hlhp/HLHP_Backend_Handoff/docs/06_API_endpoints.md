# 06 — API Endpoint Contract

The real app API is the **Engagement Service** (`/v2/*`) which wraps the stateless
**SFI engine** (`/v1/*`). There is **no `/api/hlhp/*`** surface — that was a
demo-only naming convention. This is the contract the frontend expects.

> Reference implementation: `reference/engine/engagement_service/engagement_api.py`
> (`/v2/*`) and `reference/engine/hlhp_engine.py` (`/v1/alert`).
> Base URL in the UI: `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).

---

## Engine (stateless scoring) — `/v1/*`

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/alert` | score one reading: in `{sensors, profile, alert_level, zone}` → out `{score, personal_sfi, severity_band, risk, risk_label, confidence, alert_text, action_cluster, cell_source, library_version}` |
| GET | `/v1/health` | liveness |

## Engagement service (stateful app API) — `/v2/*`

| Method | Path | Screen | Key request | Key response |
|---|---|---|---|---|
| POST | `/v2/onboarding/complete` | Onboarding | `{user_id, skin_type, concern, age_band, gender_state/life_stage, city}` | `{user_id, zone, zone_resolved}` |
| GET | `/v2/today` | **Hello** | `?user_id=&force_surge=` | `{date, city, zone, sfi, personal_sfi, band/mode, mascot_mood, risk, risk_label, confidence, coach_line, l0, l1, tip, action_cluster, impacts[], dominant, evidence_cell{id,pmids,confidence,evidence}, sensors, time_window}` |
| POST | `/v2/logs` | **Log** | `{user_id, symptoms[], areas[]}` | `{logged{…}, streak}` |
| GET | `/v2/streak` | **Streak** | `?user_id=` | `{current_streak, longest_streak, badges{first_log,streak_7,streak_30}, days_to_next_badge, week_grid[]}` |
| GET | `/v2/patterns` | **Patterns** | `?user_id=` | `{ready, logs_needed?, n_logs?, patterns[]}` |
| GET | `/v2/recap` | **Recap** | `?user_id=&days=30` | `{days, avg_sfi, logged_days, surge_days, series[], events[], verdict{}}` |
| GET | `/v2/weekly-card` | **Share** | `?user_id=` | `{week_avg_sfi, trend_vs_prev, series[7], logged_days}` |
| GET | `/v2/surge/check` | (cron→push) | `?user_id=&drop_threshold=15&force_surge=` | `{surge, current_sfi, baseline_sfi, drop, band, push{title,body}?}` |
| GET | `/v2/learn` *(new)* | **Learn** | `?user_id=` | `{explainers[], nuggets[]}` — explainers = real L2 cell text for the user's logged symptoms; nuggets = Did-You-Know cards, dominant-driver first |
| GET | `/v2/health` | — | — | `{status, library, engine_library_version}` |

> `/v2/today` is the workhorse — it runs the full SFI calculation (doc 01),
> including the gender/life-stage delta and the time-of-day overlay, and it
> **writes today's SFI into `daily_sfi`** so the day counts for Streak/Recap.

### Surge handling

There is no separate Surge screen in v3.5 — the surge state is folded into Hello.
`/v2/surge/check` remains as the **cron/monitor** endpoint: sample the SFI, compare
to the 7-day rolling baseline, and if `baseline − now >= drop_threshold` emit a
push. The `force_surge=true` query param is a demo hook that overrides
`{aqi:380, uv_index:11}` to simulate a spike.

### Live-data swap (frontend)

The UI ships fully mocked. To point it at this backend: set
`NEXT_PUBLIC_USE_MOCK=false` and `NEXT_PUBLIC_API_BASE`. The client method →
route mapping and the small response adapters are documented in
`reference/ui-logic/hlhpClient.ts` (header comment + per-method `if (!USE_MOCK)`
branches).
