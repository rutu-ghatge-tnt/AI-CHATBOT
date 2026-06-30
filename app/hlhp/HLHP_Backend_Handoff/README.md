# HLHP — Backend Developer Handoff

Everything a backend engineer needs to build the production HLHP / **Skin
Friendliness Index (SFI)** services that the frontend expects. This folder is
**documentation + reference code**, self-contained.

```
HLHP_Backend_Handoff/
├── README.md                  ← you are here (start)
├── docs/
│   ├── 01_SFI_calculation.md  ← THE core: how the 0–100 SFI is computed
│   ├── 02_Log_screen.md
│   ├── 03_Streak_screen.md
│   ├── 04_Recap_screen.md
│   ├── 05_Patterns_screen.md
│   ├── 06_API_endpoints.md    ← the /v2/* + /v1/* contract the UI calls
│   └── 07_data_model.md       ← stores + the evidence library tables
└── reference/
    ├── engine/                ← the actual FastAPI engine + engagement service
    │   ├── hlhp_engine.py             stateless scoring (POST /v1/alert)
    │   ├── engagement_service/        stateful app API (/v2/*) — serves the screens
    │   ├── mock_cache.py · seed_library_to_mongo.py · requirements.txt
    │   └── backend-docs/              architecture, SFI calibration, handoff notes
    ├── evidence/              ← scoring inputs
    │   ├── SkinBB_HLHP_Scenario_Library_v3_5.xlsx   source of truth
    │   ├── hlhp-evidence.json          exported, what the UI reads
    │   └── export_evidence.py          xlsx → json exporter
    └── ui-logic/              ← the UI's computation modules (the visual spec)
        ├── evidence.ts                 computeSFI, bandFor, lookupCell, gender/time
        ├── hlhpClient.ts               scanFromEvidence (assembles a /today response)
        └── types.ts
```

---

## Read order

1. **`docs/01_SFI_calculation.md`** — the band-points model, mode ladder, impact
   levels, scenario-cell lookup, Personal SFI, the gender/life-stage delta, and
   the time-of-day overlay. Has worked examples you can verify against the JSON.
2. **`docs/06_API_endpoints.md`** — the full `/v2/*` + `/v1/*` contract.
3. **`docs/07_data_model.md`** — `users` / `logs` / `daily_sfi` + the evidence
   library tables and their keys.
4. **Per-screen logic:** `02_Log` → `03_Streak` → `04_Recap` → `05_Patterns`.

Each doc gives: the **canonical reference** (what `engagement_api.py` /
`hlhp_engine.py` actually do) **and** the **production target** (the richer v3.5
behaviour the UI implements), so you know both where to start and where to land.

---

## The shape of the system

```
weather/AQI feed ─┐
user profile ─────┼─► SFI calculation (doc 01) ──► /v2/today ──► Hello screen
evidence library ─┘        │  writes daily_sfi
                           ▼
                       daily_sfi (per-user time series)
                           │
   logs (symptom events) ──┼──► /v2/streak  (consecutive-day algorithm)  doc 03
        │                  ├──► /v2/recap   (30-day series + driver colours) doc 04
        │                  └──► /v2/weekly-card (Share)
        └────────────────────► /v2/patterns (symptom × environment miner) doc 05
```

- **SFI** is a pure function of weather × profile × evidence-library + time. It's
  stateless — the engine (`/v1/alert`) already computes the core; the engagement
  service adapts it to `/v2/today` and persists the result.
- **Streak / Recap / Patterns** are all derived from two stores the log/check-in
  write path fills: `logs` (raw events, with the environment bands snapshotted)
  and `daily_sfi` (one SFI per day).

---

## Run the reference backend (no DB needed)

```bash
cd reference/engine
pip install -r requirements.txt

# tests (zero-config — uses the bundled library + in-memory stores):
PYTHONPATH=. pytest -q                      # ~402 passed

# the app API the screens map to, on :8000
HLHP_LIBRARY=../evidence/SkinBB_HLHP_Scenario_Library_v3_5.xlsx \
  PYTHONPATH=. uvicorn engagement_service.engagement_api:app --reload
```

Then exercise it:
```bash
curl -X POST localhost:8000/v2/onboarding/complete \
  -H 'content-type: application/json' \
  -d '{"user_id":"u1","skin_type":"Combination","concern":"Acne","city":"Pune"}'
curl 'localhost:8000/v2/today?user_id=u1'
curl 'localhost:8000/v2/today?user_id=u1&force_surge=true'
```

> The reference seeds **v3.3.1** of the library by default; point `HLHP_LIBRARY`
> at the **v3.5** xlsx in `reference/evidence/` to score on the latest content
> (same schema, additive). See `docs/07` for the version note.

---

## What's reference-only vs production

| Reference (here) | Production |
|---|---|
| in-memory `USERS/LOGS/DAILY` dicts | MongoDB collections (`users`, `logs`, `daily_sfi`) — doc 07 |
| `MockLibraryCache(xlsx)` | engine `LibraryCache` (Mongo + Redis); seed via `seed_library_to_mongo.py` |
| `zone_weather` representative values | live weather + AQI feed for the user's actual location |
| `_streak` / single-driver Patterns miner | the generalised miners in docs 03/05 + a daily-SFI cron |
| `force_surge` demo hook | real surge monitor (`/v2/surge/check` on a cron) + FCM push |
| single `symptom` per log | `symptoms[] + areas[]` per log (doc 02) |

---

## Locked rules (must hold server-side)

SFI capitalised; proper-noun mode names; no product/brand names; the word
"advice" is never used; user-facing text is zone-phrased (no city names). Full
list in `docs/07_data_model.md`.
