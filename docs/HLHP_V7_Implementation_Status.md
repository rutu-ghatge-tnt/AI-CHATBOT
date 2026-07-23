# HLHP V7 Implementation Status

**Reference:** `D:\AI-Tools\new-hlhp-ref-with-goals` (V7 Light/Dark Wired, Dermat Panel, Admin, Control Room, Backend Handoff §8–9)  
**Date:** 14 Jul 2026  
**Repos audited:**

| Repo / platform | Role |
|-----------------|------|
| `D:\AI-Tools` | Python HLHP engine + `/api/hlhp/*`, `/api/v2/*`, doctor routes, bus client |
| `D:\skinbb-main-website` | Seeker Next.js app — Fun V7 coach (`/hlhp`) + Goals shell (`/hlhp/goals`) |
| `new-hlhp-ref-with-goals` | Prototypes + reference backend (hub `:7103`, seeker `:7101`, dermat `:7102`) |
| SkinBB Node hub (`NEXT_PUBLIC_HLHP_HUB_URL` / `HLHP_HUB_URL`) | Cross-app realtime bus (events + WS) — **external to AI-Tools** |
| Dermat app | Not in seeker site — reference HTML + `mobile/dermat` only |
| Admin console | Not in seeker site — reference HTML + admin-service only |

---

## 1. Target product (what V7 “with goals” means)

End-to-end product is **three clients on one bus**, not a single website:

```text
Seeker V7  ──►  Hub (bus)  ◄──  Dermat panel
                    │
                    └──►  Admin console
```

| Client | Primary jobs |
|--------|----------------|
| **Seeker** | Today/SFI, Log, Streak, Recap, Patterns, Share, Learn · Goal wizard · Plus pay · Dermat pick · Shared chat |
| **Dermat** | Onboard · Accept seekers · Chats + CRT · Plan approval · Fee → subscription · Earnings |
| **Admin** | Overview KPIs · Seekers · Doctors · Payments 80/20 · CRT · Chat QC · Audit |

**Canonical bus keys** (Handoff §8 / `hlhp-keys`):

| Key | Shape | Writers |
|-----|-------|---------|
| `hlhp_goal_setup_v1` | Snapshot | Seeker |
| `hlhp_payment_v1` | Snapshot (pay/cancel/winback/renew) | Seeker |
| `hlhp_subscription_v1` | Live fee | Dermat |
| `hlhp_panel_accept_v1` | Accept | Dermat |
| `hlhp_plan_approval_v1` | Glow-plan sign-off | Dermat |
| `hlhp_doctor_onboard_v1` | Doctor profile | Dermat |
| `hlhp_doctor_earnings_v1` | Earnings | Dermat |
| `hlhp_daily_log_v1` | Append (optional selfie) | Seeker |
| `hlhp_shared_chat_v1` | Append messages | Seeker + dermat |
| `hlhp_typing_v1` | Transient | Both |
| `hlhp_chat_reads_v1` | Merge reads | Both |

Reference UX: **V7 Light Wired** + Dermat DC + Admin DC, exercised in Control Room.  
Reference contract: `backend/README.md` + `Backend Handoff.dc.html` §8–9.

---

## 2. Executive status

| Slice | Status | One-line |
|-------|--------|----------|
| SFI engine + alerts + scan | **Done** | Live weather → score → scenarios → Fun Hello |
| Fun coach tabs (Hello→Learn) | **Mostly done** | Live APIs; P0 Fun polish shipped |
| Weather metrics (WeatherAPI) | **Done** | Temp/RH/UV/AQI/wind from `WEATHERAPI_KEY`; Skintruth = location + visuals |
| Live city chart | **Done** | `GET /api/v2/cities` + HelloCityChart live path |
| Goals / Plus UI shell | **Partial** | Wizard + chart hub exist; pay/dermat/chat mostly local/demo |
| Shared chat (real) | **Partial backend / missing product UI** | AI-Tools chat routes + hooks; Fun Goals overlay is fake |
| Dermat panel product | **Scaffold API / no seeker-site UI** | Doctor routes in AI-Tools; no dermat front-end in skinbb |
| Admin console | **Missing** | Hooks vendored; no admin app in production repos |
| Selfie S3/server | **Done** | `POST/GET/DELETE /api/v2/selfies`; Recap timeline auth-fetches media blobs |
| Hub end-to-end | **Partial** | Client + keys exist; needs live hub + role lanes wired |

Rough completion (product capability, not LOC):

| Area | ~% toward V7 reference |
|------|-------------------------|
| Seeker SFI / Fun tabs | ~90% |
| Weather + city board | ~90% |
| Goals → Plus → dermat journey | ~40% |
| Shared chat | ~25% |
| Dermat panel | ~20% (API scaffold) |
| Admin | ~10% (Ops doctors/services partial) |
| Cross-app bus live in prod | ~30% |

---

## 3. Already implemented (by surface)

### 3.1 Seeker Fun coach — `skinbb-main-website` `/hlhp`

**Entry:** `HlhpFunClient` → `FunAppFrame` · tabs in `src/lib/hlhp/fun/tabs.ts`

| Tab | Status | Backed by |
|-----|--------|-----------|
| **Hello / Today** | Live | `POST /api/hlhp/scan`, `GET /api/v2/today`, city chart, scenery |
| **Log** | Live | `POST /api/v2/logs` / v1 log · selfie via `/api/v2/selfies` |
| **Streak** | Live | `/api/v2/streak` (+ v1 fallback) |
| **Recap** | Live | history/catchup APIs + server selfie timeline |
| **Patterns** | Live | patterns + narration + alert toggles |
| **Share** | Live | `/api/v2/share` / weekly card |
| **Learn** | Mostly live | learn API; some static lifestyle copy |

**V7 polish already shipped in Fun UI (this thread and prior work):**

- Halo SFI orb (design colors)
- Impact bars (shimmer / dominant / High pulse)
- Richer alert chips
- Expandable city chart (Top 3 ↔ All)
- Goal CTA / wedding-style entry + toolbar chip → `/hlhp/goals`
- Log factors (sleep/food/routine-skip), live camera selfie capture (local save)
- Scene/weather ambience (with humidity-vs-rain fix)
- Demo-only ProfileBar / quick-settings ambience panel removed

### 3.2 Weather architecture — `AI-Tools`

| Concern | Source | Status |
|---------|--------|--------|
| Temperature, humidity, UV, AQI, wind | **WeatherAPI** (`WEATHERAPI_KEY`) | Done |
| Location label polish + background + animal | **Skintruth** location-weather | Done |
| Forecast / plan week / SFI timeline | WeatherAPI forecast + history | Done |
| Multi-city SFI board | `GET /api/v2/cities` via `city_chart_service` | Done |
| Home weather strip proxy | `GET /api/v1/weathers/location-weather` | Done |

Key files: `app/hlhp/services/weather_fetcher.py`, `city_chart_service.py`, `weatherapi_forecast.py`, `config.py`.

### 3.3 Engine / composition APIs — `AI-Tools`

**Done:** guest + personalized alerts · scan · symptom taps · composition lanes (explore, week, plan_week, timeline, patterns, log, streak, learn, consent) · V4 today/logs/cities/streak/recap/share/learn.

### 3.4 Goals / Plus / bus scaffolding

| Piece | Where | Status |
|-------|-------|--------|
| Goals page + wizard + chart hub UI | `skinbb` `/hlhp/goals` | UI present |
| `POST /api/v2/goals`, `/v2/profile` | AI-Tools | Done (hub publish optional) |
| `GET /api/v2/plus`, checkout proxy | AI-Tools | Partial (needs Node URL) |
| Bus client + key ACL | `app/hlhp/core/bus_*` | Done |
| Vendored react hooks (~100) | `skinbb` `src/lib/hlhp/react/` | Present, mostly unused in UI |
| `useGoalSetup` / `usePayment` / local or hub bus | Goals module | Soft-wired |

### 3.5 Doctor / chat API scaffolds — `AI-Tools`

| Route area | Status |
|------------|--------|
| Seeker chat GET/POST messages/read/typing | Partial — hub-dependent |
| Doctor panel accept / plan approve / subscription / chat / CRT / onboard | Partial scaffold — **panel seekers list empty** |
| Auth deps (seeker + doctor role) | Done |

---

## 4. Remaining work (prioritized)

### P0 — Close the Fun / V7 polish gaps (seeker)

| Item | Gap vs V7 Light | Status |
|------|-----------------|--------|
| What’s Different Today | Multi-rule REINFORCE / PROTECT / SKIP from evidence | **Done** — `routine_rules_v1.json` + `select_routine_today` on scan → `whats_different`; Hello multi-rule cards |
| My routine overlay | Coming soon (button hint) | Deferred — no editor this wave |
| Selfie compare | Side-by-side from daily log extras | **Done** — photos + log chips only, **no AI** |
| Selfie server upload | Python → S3 | **Done** — `POST/GET/DELETE /api/v2/selfies`; Recap auth-blob fetch |
| Barrier / selfie AI check | Out of scope | Compare is visual only |
| SFI formula alignment | Ref V7 `W_DOM=0.6` vs production | **Canonical = additive V4** via `resolve_sfi` (scan + city chart + orb). W_DOM remains reference-only |
| Learn articles | Partial mock | Thin cleanup — API levers preferred; Knowledge Feed via Explore CMS |
| Recap demo strip | Synthetic month toggle | **Done** — removed FunDemoStrip / forceDemo path |

### P1 — Goals → Plus → dermat journey (cross-app)

| Step | Reference behavior | Current | Remaining |
|------|-------------------|---------|-----------|
| 1. Build chart | Write `hlhp_goal_setup_v1` | Soft POST + bus/local | Harden hub publish + admin/dermat visibility |
| 2. Dermat roster | Live doctors + waitlist | Hardcoded `DERM_AVAILABLE` | Doctor marketplace API + waitlist |
| 3. Fee | Dermat sets `hlhp_subscription_v1` | Plus reads hub if present | Dermat UI to set fee |
| 4. Pay | Real checkout → `hlhp_payment_v1` | Bus flag / celebration only | Razorpay (or Node) + publish payment snapshot |
| 5. Accept | Dermat accept → seeker notif + chat unlock | API exists; UI missing | Dermat panel seeker list + accept UX |
| 6. Plan approval | Dermat → chart “From your dermat” | API exists | Dermat tasks UI + seeker chart surface |
| 7. Shared chat | Real messages + typing + reads + CRT | Fake overlay auto-reply | Wire `useChat` to `/api/v2/chats*` + hub WS |

### P2 — Dermat platform (new or dedicated front-end)

Reference: `HLHP Dermat Panel` + `mobile/dermat` · Backend routes partially in AI-Tools `/api/hlhp/doctor/*`.

| Feature | Remaining |
|---------|-----------|
| Dermat SPA / routes in a real app | Build product UI (seeker site has no dermat screens) |
| Panel aggregation | Fill `seekers: []` from hub lanes + goal/payment state |
| Onboarding (photo, clinics, services, fee) | Complete + publish onboard key |
| Chats + CRT timer (2h / business hours) | Wire + SLA metrics |
| Earnings / payouts 80/20 | Publish `hlhp_doctor_earnings_v1`; APIs missing in AI-Tools |
| Availability calendar | Missing |
| Reviews | Missing |

### P3 — Admin platform

Reference: `SkinBB Admin Panel` + `admin-service` `:7103`.

| Feature | Remaining |
|---------|-----------|
| Admin app (desktop) | Not in skinbb / AI-Tools |
| Overview KPIs, seekers, doctors, payments | Hub read-models + UI |
| Chats & CRT, Chat QC, audit | Hub + QC review routes |
| Win-back cohorts, refunds | Admin hooks exist in vendor lib only |

### P4 — Hub / ops hardening

| Item | Remaining |
|------|-----------|
| Production hub always-on | Confirm Node mount `/api/v1/hlhp/hub` + env on web + AI-Tools |
| Multi-seeker lanes | `state.seekers[<id>]` |
| Publish daily logs to bus | AI-Tools logs Mongo only today — add `hlhp_daily_log_v1` |
| Chat attachments beyond `photo: bool` | Binary / selfie URL attach |
| Push / FCM | Reference stub only |
| Control Room style QA | Optional internal tool |

---

## 5. Matrix: reference feature → each platform

Legend: **Done** · **Partial** · **Missing** · **N/A**

| Feature | Ref prototype | AI-Tools API | Seeker FE | Dermat FE | Admin FE |
|---------|---------------|--------------|-----------|-----------|----------|
| Scan / SFI / alert | Done | Done | Done | N/A | N/A |
| Weather metrics (WA) | Demo zones | Done | Done | N/A | N/A |
| Visuals (Skintruth) | Bundled assets | Done | Done | N/A | N/A |
| City chart live | Demo zones | Done | Done (+ fallback) | N/A | N/A |
| Log + factors | Done | Done (Mongo) | Done | Read via bus (ref) | Feed (ref) |
| Selfie server | Done (`/v2/selfies`) | **Done** | Done (auth blob) | Missing | Missing |
| Streak / Recap / Patterns / Share / Learn | Done | Done | Mostly done | N/A | N/A |
| What’s Different today | Done | **Done** (`whats_different`) | **Done** | N/A | N/A |
| Goal wizard | Done | Partial | Partial UI | Listens (ref) | Feed (ref) |
| Plus payment | Done (demo pay) | Partial proxy | Demo/bus | Toast (ref) | Payments (ref) |
| Dermat pick | Done | Missing roster in Python (Node marketplace) | Static / API | Accept API partial | Missing |
| Shared chat | Done | Partial | Fake overlay | Scaffold API | QC (ref only) |
| Plan approval | Done | Partial | Chart shell | Scaffold | Missing |
| Doctor onboard / earnings | Done | Partial / Missing | N/A | Missing product | Missing |
| Admin KPIs / QC / audit | Done | Missing | N/A | N/A | Missing |
| Bus keys live | Done | Partial client | Soft / local | Missing UI | Missing |

---

## 6. Suggested delivery waves

### Wave A — Seeker “V7 Fun complete” (1–2 sprints)
1. ~~Selfie upload + Recap timeline from server~~ **Done**
2. ~~What’s Different live~~ **Done** · My routine editor still deferred
3. ~~Kill Recap demo strips~~ **Done**
4. ~~Align SFI formula~~ **Done (canonical additive V4 documented)**

### Wave B — Goals money path (2–3 sprints)
1. Hub required in staging  
2. Real checkout → `hlhp_payment_v1`  
3. Dermat roster/waitlist from API  
4. Wire seeker chat overlay to real `/v2/chats`

### Wave C — Dermat product (3+ sprints)
1. Panel UI (seekers, chats, tasks, profile)  
2. Fill panel aggregation + accept/approve  
3. Earnings + CRT dashboards  
4. Onboarding complete

### Wave D — Admin + ops (parallel / after C)
1. Stand up admin against hub read models  
2. Payments 80/20 + QC + audit  
3. Control-room style regression harness

---

## 7. Key paths (quick map)

### Reference
- Seeker UX: `new-hlhp-ref-with-goals/extracted-v7-light.html`, `HLHP V7 Light Wired.html`
- Dermat: `HLHP Dermat Panel.dc.html`
- Admin: `SkinBB Admin Panel.dc.html`
- Contract: `Backend Handoff.dc.html`, `backend/README.md`, `backend/react/hlhp-keys.js`

### AI-Tools
- Routers: `app/hlhp/api/{scan,composition,v4_routes,weather}.py`
- Weather: `app/hlhp/services/weather_fetcher.py`, `city_chart_service.py`
- Goals / chat / payments / hub: **Node only** (removed from AI-Tools)

### Seeker site
- Fun: `src/components/hlhp/fun/**`, `src/lib/hlhp/fun/**`
- Goals: `src/components/hlhp/modules/goals/**`
- Services: `src/services/hlhp-v1.service.ts`, `hlhp-v2.service.ts`, `hlhp-goals.service.ts`
- Hooks (mostly unused): `src/lib/hlhp/react/**`

---

## 8. Config checklist (staging)

| Variable | Where | Purpose |
|----------|-------|---------|
| `WEATHERAPI_KEY` | AI-Tools `.env` | Live metrics + city board (strip spaces) |
| `HL_WEATHER_API_URL` | AI-Tools | Skintruth visuals |
| `HLHP_SELFIE_STORAGE_DIR` / S3 vars | AI-Tools | Fun coach selfies |
| `NEXT_PUBLIC_API_URL` | Seeker web | Node goals / chat / Plus |
| `NEXT_PUBLIC_HLHP_HUB_URL` | Seeker web | Socket.IO (optional override) |

---

## 9. Bottom line

- **The seeker SFI product** (scan → Hello → Log → Streak → Recap → Patterns → Share → Learn, plus WeatherAPI + live city chart + selfies + What’s Different rules) is the mature slice and is near V7 Fun completeness (My routine editor still deferred).
- **Canonical SFI** is additive V4 via `resolve_sfi` — not the V7 reference `W_DOM` blend.
- **Goals / dermat / chat / admin** in the reference folder describe a **multi-app bus product**. Today you have: seeker Goals **shell**, AI-Tools **API scaffolds**, Node doctor marketplace, vendored **hooks**, and a **reference** hub/dermat/admin — not a finished cross-platform journey.
- Next highest leverage: **real Plus payment + live chat + dermat panel aggregation**, with hub on in staging.

*This document is a living status snapshot (updated 15 Jul 2026). Update after each wave.*
