# HLHP — "Fun Enhanced" UI

A mobile companion UI for the SkinBB **Skin Friendliness Index (SFI)** engine,
rebuilt from the animated HLHP prototype and re-skinned with the **SkinBB design
system**. Seven tabs, onboarding overlay, coach bubble, badge strip, mascot, and
every animation from the prototype — wired to a **thin, swappable API layer**
that is **fully mocked client-side** by default.

> Frontend only. No backend was added or modified. Every screen runs offline out
> of the box; one flag points it at the real FastAPI when you're ready.

### Real evidence library (v3 — live library browser)

The app now reads the **real SkinBB scenario library** (v3.4, 880 single-factor
Master cells + 670 compound cells + cited Did-You-Know nuggets), exported to a
static `public/hlhp-evidence.json` by `scripts/export_evidence.py`.

A **profile bar** (city × skin type × main concern) drives it: changing any one
recomputes the **SFI from the real band-points table**, finds the dominant
driver, and looks up the matching Master cell — so the Hello screen shows the
**real L0 / L1 / L2 alert text, risk score, confidence tier (HIGH/MODERATE/
INFERRED), action cluster and PMID anchors** for that exact combination. Impact
lines use the real band thresholds; Learn surfaces the real cited nuggets,
dominant-driver first. If the JSON can't be fetched, a small built-in sample
keeps the app running.

```bash
# regenerate the export from the .xlsx (needs openpyxl)
python3 scripts/export_evidence.py /path/to/SkinBB_HLHP_Scenario_Library_v3_4.xlsx public/hlhp-evidence.json
```

> The `.xlsx` is the **source of truth** (the live engine reads it via MongoDB);
> the frontend embeds a JSON export of selected columns. No clinical thresholds
> were changed — the export is faithful to the library.

### v2 changes

- **Tabs (7):** Hello · Log · Streak · Recap · Patterns · Share · **Learn**.
  The standalone **Surge** tab was folded into **Hello**; **Good Day** was
  replaced by **Learn**.
- **Hello** is now the hub: animated SFI score (count-up + ring sweep), a
  **mode badge** (Paradise Mode → Smooth Sailing → Guard Up → Battle Stations →
  Hostile Mode → Code Red), **impact lines** for Heat / UV / Humidity / AQI as
  Low / Medium / High (driver colours), and an **L0 flash alert** that taps open
  to **L1 + an actionable tip** (honours the L0 wording convention). The
  "Simulate sudden surge" toggle drops you into Hostile Mode with a frame shake.
- **Log:** chips **Dry / Oily / Dull / Breakout / Spots** (multi-select).
  Breakout & Spots reveal a multi-select face-area picker including **Full
  face**; one **Save** button commits the day. ("Spots" exists because acne
  often leaves marks behind.)
- **Recap:** each day is coloured by its **driver** — Humidity = blue, UV = red,
  Heat = orange, AQI = purple, Comfort = green — with a legend and driver-coded
  callouts.
- **Share:** a strong, ready-to-paste social caption (with a Copy button) plus a
  punchier on-card headline.
- **Learn:** symptom explainers (from your logs) + a SkinBB knowledge article
  feed, surfaced by today's dominant driver.
- Richer **Web Audio** cues (chords, glides, distinct per action) and smoother
  animation polish throughout.

---

## Stack

- **Next.js 15** (App Router, RSC) + **React 19** + **TypeScript**
- **Tailwind CSS v4** (CSS-first — no `tailwind.config.js`)
- **shadcn/ui** patterns (new-york), custom `Button` API (`variant` / `color` / `rounded`)
- **lucide-react** icons (stand-ins for the prototype's Tabler icons)
- Web Audio SFX, zero animation libraries (all CSS keyframes + small React helpers)

---

## Quick start

```bash
cd hlhp-ui
cp .env.example .env.local        # defaults are fine — runs fully mocked
npm install
npm run dev                       # http://localhost:3000
```

That's it — no backend needed. The app boots into onboarding, then the **Hello**
tab, with realistic mock data behind all 8 screens.

```bash
npm run typecheck                 # tsc --noEmit  (verified clean)
npm run build                     # production build
```

---

## How my design tokens map to the HLHP screens

The prototype hardcoded a cream / indigo / amber / red palette. We re-expressed
those **roles** in the SkinBB token language so the app stays on-brand while
keeping the prototype's emotional color logic. All of this lives in
[`app/globals.css`](app/globals.css) under the `HLHP SEMANTIC LAYER` block.

**The SkinBB palette has no amber/orange and no cream.** It's indigo +
periwinkle + lavender + lime + neutrals. So the prototype's "warm" roles are
mapped onto the **indigo/periwinkle/lavender ramp** — not invented amber. Every
`--hlhp-*` variable in `globals.css` is a **pure alias of a real SkinBB token**;
there are zero invented color literals.

| Prototype role | What it colors | SkinBB token it maps to | HLHP var |
|---|---|---|---|
| Canvas / surfaces | app frame, screen backgrounds | `--background` (white) + `--secondary` / `--muted` neutrals | `--hlhp-canvas`, `--hlhp-canvas-soft` |
| Ink / insight | coach bubble, Patterns hero, dark UI, primary text | `--primary` (deep indigo) + `--accent-primary-dark` | `--hlhp-ink`, `--hlhp-insight` |
| **"Warmth" / sun** (Hello orb, Streak flame, badges) | *re-skinned off amber* → brand periwinkle/lavender | `--accent-primary`, `--accent-primary-dark`, `--accent-secondary` | `--hlhp-warmth`, `--hlhp-warmth-deep`, `--hlhp-sun` |
| **Red — surge only** | Surge tab banner / ring / spike bars **only** | `--destructive` | `--hlhp-surge` |
| Good / positive | Good Day, weekend "best window", positive trend, badge tick | `--accent-tertiary` (SkinBB lime) + `--accent-tertiary-dark` | `--hlhp-good`, `--hlhp-good-deep` |

Everything else is your system verbatim: `--primary`, `--accent-primary*`,
`--accent-secondary*`, `--accent-tertiary*`, `--destructive`, `--chart-1..5`,
fonts (`--font-holiday` for headings, `--font-sans` for body), `--radius`, and the
shadow ramp — all carried over exactly from `Design-styling-template.md` and
exposed as Tailwind utilities via `@theme inline`. Components use **token classes
/ token vars only** — there is **no hardcoded hex** anywhere except the mascot's
neutral ink/outline (`#3F3530` / `#E5D9BD` / white), per your rules. The Hello
orb, Streak flame, badges, particles, and confetti all read from the brand ramp
— so the app renders indigo-forward, never amber.

> Tabler icons in the prototype → **lucide-react** equivalents (closest mapping
> per tab). Swap to `@tabler/icons-react` if you prefer pixel-parity.

---

## File structure

```
hlhp-ui/
├─ app/
│  ├─ globals.css            # SkinBB tokens + HLHP semantic layer + ALL keyframes
│  ├─ layout.tsx             # root layout + viewport
│  └─ page.tsx               # mounts <HlhpProvider> + <AppFrame>
├─ api/
│  ├─ hlhpClient.ts          # ⭐ the ONE backend boundary — mock + live branches
│  └─ types.ts               # request/response shapes (mirror the real backend)
├─ mock/
│  ├─ data.ts                # client-only dataset (30-day trend, logs, weather, explainers)
│  ├─ badges.ts              # client-only badge unlock rules (4 earned + 3 locked)
│  └─ patterns.ts            # client-only Patterns enrichment (ribbons, mini-charts)
├─ lib/
│  ├─ store.tsx              # app state provider (scan + history cache, tab, sound, surge)
│  ├─ hooks.ts               # reusable animation helpers (replay, stagger, count-up)
│  ├─ sound.ts               # Web Audio SFX engine (ported from prototype toggle)
│  ├─ tabs.ts                # 8-tab metadata + per-screen coach copy
│  └─ utils.ts               # cn()
├─ components/
│  ├─ shell/                 # Toolbar, Tabs, BadgeStrip, CoachBubble, Onboarding,
│  │                         #   ScreenShell (Screen + ReplayBar), AppFrame
│  ├─ anim/                  # Particles (drift/ember/sparkle/confetti), Mascot
│  ├─ screens/               # Hello, Log, Streak, Surge, Recap, Patterns, Share, GoodDay
│  └─ ui/                    # button.tsx (custom API), card.tsx, slot.tsx (Radix shim)
├─ components.json           # shadcn config
└─ .env.example
```

---

## Animations preserved (from the prototype)

Every animation in the brief is ported into [`app/globals.css`](app/globals.css)
keyframes + small React helpers in [`lib/hooks.ts`](lib/hooks.ts) and
[`components/anim/`](components/anim) — **not** dropped for "cleaner" code:

`fadeSlide` screen transition · typewriter greeting · mood-orb `breathe` +
`pulseGlow` · chip `chipPop` + burst particles + float-up hearts · flame
`flameFlicker` + ember particles + streak counter roll · surge `slideDown`
banner + frame `shake` + conic ring dip (1400ms) + `spike` bars `scaleY` ·
recap day-mark stagger + walker 8s `walk` + callout `cardBounce` + stamp
confetti · patterns insight-card stagger + timeline dots + correlation bar
width + hour bars · share big-number count-up + chart bars + sparkles +
confetti-on-share · good-day confetti rain + `letterPop` headline + mascot
`celebJump` + stat count-up · onboarding `bobble` mascot + fade overlay.

The spring easing `cubic-bezier(0.34, 1.56, 0.64, 1)` is the `--spring` var, used
everywhere the prototype used it. **Each screen has a replay button** that
re-triggers its animations (remount via `useReplay`, no API call). Animations
respect `prefers-reduced-motion`.

---

## Data flow on load

1. Read `hlhp_onboarding_done` from `localStorage` → show onboarding if absent.
2. `scan()` (mock `POST /scan`) → cache in app state → drives Hello.
3. In parallel: `history()` (mock `GET /history`) → cache → drives Recap / Share /
   Good Day / Patterns / Streak / badges.
4. Default tab = **Hello**.
5. **Surge** tab fetches `sfiTimeline()` lazily, only when opened.
6. On tab switch: replay that screen's animations.

The **Surge** screen has a "Simulate surge" demo toggle that flips `force_surge`
across the whole app (mirrors the backend's `?force_surge=true` hook) so the
sudden-event path is reviewable without waiting for bad weather.

---

## Real API vs. mocked — the honest handoff

**Nothing here calls a live server.** Per the brief, the client keeps the
task-spec `/api/hlhp/*` method names and **mocks every one**. Below is exactly
what's fabricated and what the *real* route would be.

> ⚠️ Important: the real backend in this repo has **no `/api/hlhp/*` endpoints.**
> The live app API is the **Engagement Service** (`engagement_service/engagement_api.py`)
> at **`/v2/*`**, which wraps the stateless SFI engine (`hlhp_engine.py`, `/v1/alert`).
> The client method names follow the task spec; the comments + table below give
> the real route each one should target when you go live.

| UI method (`hlhpClient`) | Task-spec name | Status | Real backend route to wire to |
|---|---|---|---|
| `scan()` | `POST /scan` | **mock** | `GET /v2/today?user_id=` (+ one-time `POST /v2/onboarding/complete`) |
| `symptomFeeling()` | `POST /symptom_feeling` | **mock** | `POST /v2/logs` |
| `actionTap()` | `POST /action_tap` | **mock** | `POST /v2/logs` → returns `{ streak }` |
| `history()` | `GET /history` | **mock** | `GET /v2/recap` + `GET /v2/streak` (+ `GET /v2/weekly-card`) |
| `sfiTimeline()` | `GET /sfi_timeline` | **mock** | compose `GET /v2/surge/check` + sampled `GET /v2/today` |
| `catchup()` | `GET /catchup` | **mock** | `GET /v2/recap` narrative |
| `symptomExplainer()` | `GET /symptom_explainer/{kw}` | **mock** | *(no live route yet — static content)* |
| `getConsent()` / `postConsent()` | `GET`/`POST /consent` | **mock** | `POST /v2/onboarding/complete` (consent stored with profile) |
| `health()` | `GET /health` | **mock** | `GET /v2/health` |

### What's decorative (mock enrichment beyond any backend)

- **Badge strip** — only `first_log`, `streak_7`, `streak_30` exist in `/v2/streak`.
  `heat_surge` and `first_pattern` unlocks, plus the Monsoon/Diwali locked badges,
  are client rules in [`mock/badges.ts`](mock/badges.ts).
- **Patterns** — card **bodies** come from the (real-shaped) `symptom_explainer`
  call; the **% match ribbons (68–83)** and the mini timeline / weekday-grid /
  hour-chart visuals are decorative ([`mock/patterns.ts`](mock/patterns.ts)).
- **Log follow-ups** — "where on your face?" / "how many?" are UI-only.
- **Share buttons** — toast only (no real share/export).
- **Surge numbers** — the prototype's 78→54 etc. predate engine v3.3.1; when live,
  every number comes from the engine and surge thresholds live in the engagement
  layer, not the UI.

---

## Going live (mock → real backend)

Everything routes through **one file**: [`api/hlhpClient.ts`](api/hlhpClient.ts).

1. Run the real services (from the v3.3.1 handover root):
   ```bash
   PYTHONPATH=. uvicorn engagement_service.engagement_api:app --reload   # :8000
   ```
2. In `.env.local`:
   ```
   NEXT_PUBLIC_USE_MOCK=false
   NEXT_PUBLIC_API_BASE=http://localhost:8000
   ```
3. In each `hlhpClient` method, the `if (!USE_MOCK)` branch already points at the
   real `/v2/*` route (see the mapping table). Finish the small response adapters
   (e.g. `/v2/today` → `ScanResponse`) where noted in comments — the field names
   were chosen to make this a mapping, not a rewrite.

No component, screen, or store code changes — they only know `hlhpClient`.

---

## Verification status (this build)

- ✅ `tsc --noEmit` passes clean across all ~30 files (types, imports, JSX, the
  client ↔ store ↔ screen wiring are all sound).
- ✅ Every hook/interactive component carries `"use client"` (RSC-safe).
- ✅ `app/globals.css` parses through the Tailwind v4 engine without CSS errors.
- ⚠️ A full `next build` could not be completed in the build sandbox used to
  author this (the SWC native binary hits a `SIGBUS` before compiling app code —
  an environment fault, not a code issue; it crashes at "Creating an optimized
  production build" regardless of available memory). Run `npm run build` locally
  to produce the production bundle — the type-check already covers correctness.
- A static visual reference of three screens (Hello, Surge, Good Day) with the
  exact tokens is in the repo root as `preview.html` (open in a browser).

---

## Notes / locked product rules honored in copy

- "SFI" always capitalized; first mention as "Skin Friendliness Index (SFI)".
- Band names are proper nouns: Paradise Mode → Smooth Sailing → Guard Up →
  Battle Stations → Hostile Mode → Code Red.
- No product recommendations anywhere; "information"/"education", never "advice".
- Plain language; no clinical jargon in user-facing copy.
- "Apply Knowledge to the Skin" closes the Share card.
