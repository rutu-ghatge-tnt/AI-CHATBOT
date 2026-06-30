# HLHP Engagement Service (reference implementation)

The stateful API tier that sits between the front-end and the v3.3.1 SFI engine. It
turns the engine's single-shot scoring into the longitudinal, engaging experience the
8 screens need: profiles, symptom logs, daily SFI history, streaks/badges, surge
detection, pattern mining, weekly/monthly aggregation, and the `/today` adapter.

It runs **with no MongoDB/Redis** — scoring uses `MockLibraryCache` (loads the Excel
directly) and storage is in-memory — so a developer can run the whole loop locally.

## Run

```bash
pip install fastapi uvicorn pydantic openpyxl
export HLHP_LIBRARY=../library/SkinBB_HLHP_Scenario_Library_v3_3_1.xlsx
# run from the handover ROOT so hlhp_engine.py + mock_cache.py are importable:
PYTHONPATH=. uvicorn engagement_service.engagement_api:app --reload
# tests:
HLHP_LIBRARY=library/SkinBB_HLHP_Scenario_Library_v3_3_1.xlsx \
  PYTHONPATH=. python -m pytest engagement_service/ -q
```

## Endpoints → front-end screens

| Endpoint | Method | Serves | Engine use |
|---|---|---|---|
| `/v2/onboarding/complete` | POST | Onboarding | stores profile, resolves city→zone |
| `/v2/today` | GET | Hello | adapts `AlertResponse` → SFI, personal SFI, band, mascot, coach, action |
| `/v2/logs` | POST | Log | enriches each log with live SFI + bands |
| `/v2/streak` | GET | Streak | derived from logs/check-ins + badge rules |
| `/v2/patterns` | GET | Patterns | mines symptom ↔ humidity co-occurrence over logs |
| `/v2/weekly-card` | GET | Share | 7-day SFI aggregate + trend |
| `/v2/recap` | GET | Recap | 30-day series + surge count |
| `/v2/surge/check` | GET | Surge (push) | live SFI vs rolling baseline; emits push payload |
| `/v2/good-day` + `/bottle` | GET/POST | Good day | best-stretch detection + save |
| `/v2/health` | GET | — | reports engine library version |

Demo hooks: `?force_surge=true` on `/today` and `/surge/check` simulates a bad-weather spike.

## What is reference-only (swap for production)

| Here (reference) | Production |
|---|---|
| `MockLibraryCache(xlsx)` | engine's `LibraryCache` (Mongo + Redis) |
| in-memory `USERS/LOGS/DAILY` dicts | MongoDB collections |
| `ZONE_WEATHER` mock provider | live weather + AQI feed |
| `CITY_ZONE` subset | the library's 62-city → zone map (sheet 1) |
| `_streak` / pattern miner (simple) | batch jobs + richer correlation |
| no auth / no push transport | your JWT/Firebase + FCM |

The engine is **unchanged** and used as a library — everything here is additive.
See `../docs/HLHP_Backend_Architecture_v2.md` for the full design and
`../docs/HLHP_FE_Backend_Compatibility.md` for how it maps to the prototype.
