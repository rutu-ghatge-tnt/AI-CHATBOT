# HLHP Flash Alerts — UI Screen Specifications

**Owner:** Ajit Marathe · SkinBB
**Version:** 1.0 (matches workbook v1.0)
**Last updated:** 2026-06-19
**Audience:** Frontend engineer, designer, product team, QA
**Companion docs:** `HLHP_Engine_Implementation_Spec_v2.md` (engine architecture), `HLHP_Engineering_Deployment_Guide.md` (deployment), `HLHP_Composition_Layer_Schema.md` (workbook schema)

This document is the single source of truth for every user-facing screen in HLHP Phase 1. It consolidates the 7 surfaces designed for the launch experience, with layout diagrams, content variables, API contracts, edge cases, and Phase 2 forward-looking notes.

---

## Table of contents

1. [Design system overview](#1-design-system-overview)
2. [Navigation architecture — 4 lanes + symptom-tap FAB](#2-navigation-architecture)
3. [Screen 1 — Today: Top Header](#3-screen-1--today-top-header)
4. [Screen 2 — Today: Skin Friendliness Index + Score Breakdown](#4-screen-2--today-skin-friendliness-index--score-breakdown)
5. [Screen 3 — Today: Three Alerts + Symptom Chips](#5-screen-3--today-three-alerts--symptom-chips)
6. [Screen 4 — Your Skin: Concern Deep-Dive](#6-screen-4--your-skin-concern-deep-dive)
7. [Screen 5 — Symptom-Tap Deep-Dive](#7-screen-5--symptom-tap-deep-dive)
8. [Screen 6 — Explore Lane](#8-screen-6--explore-lane)
9. [Screen 7 — History Lane](#9-screen-7--history-lane)
10. [API contract summary](#10-api-contract-summary)
11. [Empty / edge / error states](#11-empty--edge--error-states)
12. [Guest mode vs Personalised mode rendering](#12-guest-mode-vs-personalised-mode-rendering)
13. [Phase 1 vs Phase 2 differences](#13-phase-1-vs-phase-2-differences)
14. [Implementation checklist for frontend](#14-implementation-checklist-for-frontend)

---

## 1. Design system overview

### Color palette

The app uses a cream-and-navy primary system inspired by the existing SkinBB visual language, with semantic accent ramps for different content states.

| Token | Hex | Use |
|---|---|---|
| `--bg-page` | `#FBF4E8` | Section card background (cream) |
| `--bg-canvas` | `#FFFFFF` | Inner content cards |
| `--text-primary` | `#1A2B47` | Body text, headings |
| `--text-secondary` | `#4A5568` | Sub-lines, captions |
| `--text-muted` | `#7A6B4C` | Metadata, timestamps |
| `--border-subtle` | `#E5D9BD` | Card borders |
| `--accent-lime` | `#B7D34E` | Section heading underline |
| `--warn-orange` | `#E58124`, `#FBE0CF` | UV / heat indicators |
| `--info-blue` | `#2864B8`, `#ECF2FA` | Sun-screen advice, neutral context |
| `--mint-green` | `#3F6A1D`, `#D4ECDB` | Comfortable bands, fungal advice |
| `--violet-purple` | `#5240A6`, `#E2DCF3` | Pollution, science nuggets |
| `--coral-red` | `#A2342F`, `#FCEDED` | Humidity-rising, escalation panels |
| `--peach-acne` | `#9C3E0A`, `#FBE0CF` | Acne-relevant chips |

### Typography

| Element | Size | Weight |
|---|---|---|
| Hero title | 22px | 500 |
| Section heading (with lime underline) | 16px | 500 |
| Body text | 14px | 400, line-height 1.6 |
| Card title | 15px | 500 |
| Body small | 13px | 400, line-height 1.55 |
| Metadata / tags | 11px | 500, letter-spacing 0.08em, uppercase |
| Footnote / source | 12px | 400, italic |

### Component primitives

- **Section card** — cream background, lg radius (12px), 0.5px subtle border, 1.25rem 1.5rem padding
- **Inner card** — white background, md radius (8px), 0.5px subtle border, 12-14px padding
- **Pill** — 999px radius, 3px 9px padding, 11-13px font, semantic color background + 800-stop text
- **Heading underline** — 2px lime line under the text, positioned 4px below baseline
- **Left-accent panel** — 3px solid colored left border, 0 radius left side, 8px radius right side
- **Score ring** — 88px circle, conic-gradient fill, white inner circle 68px
- **Mood headline** — 22px/500, indicative voice, anchored to current day

---

## 2. Navigation architecture

### The 4 lanes

| Lane | Icon | Color | Primary purpose |
|---|---|---|---|
| Today | `ti-sun` | Warn-orange | Daily freshness — mood, SFI, alerts, symptom chips |
| Your Skin | `ti-droplet` | Info-blue | Concern depth — routine, week ahead, dermatologist triage, nugget |
| Explore | `ti-compass` | Violet-purple | Event guides + science feed + symptom browse |
| History | `ti-clock` | Gray-muted | SFI trend + sudden events + catch-up |

### Desktop top bar layout

```
┌──────────────────────────────────────────────────────────────────────┐
│ [SkinBB · HLHP]   [Today] [Your skin] [Explore] [History]   [SFI 67] [AM] │
├──────────────────────────────────────────────────────────────────────┤
│ Tap what your skin feels   [tight] [shiny] [dark spots] [breakout] ...│
└──────────────────────────────────────────────────────────────────────┘
```

The symptom-tap chip strip is **persistently visible** below the lane nav on desktop — accessible from any lane.

### Mobile bottom tab bar layout

Center-floating symptom-tap FAB pattern (Instagram / Swiggy / Zepto style):

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  [Today]  [Your skin]   [FAB]   [Explore]  [History] │
│                                                     │
└─────────────────────────────────────────────────────┘
```

The dark navy FAB icon is `ti-hand-finger` (or `ti-touch`). Tap surfaces a bottom sheet with the 20 symptom chips.

### Lane state CTA strings

Each lane's nav tab carries a small dynamic status string below it, resolved by `Lane_State_Strings.lane_state_*` rules. Example default states:

| Lane | Default CTA | Conditions |
|---|---|---|
| Today | "3 alerts ready" | Alerts fire |
| Your skin | "7-day forecast" | Default fallback |
| Explore | "12 guides + nuggets" | Default fallback |
| History | "Last 30 days" | Default fallback |

Override priorities resolve from the `Lane_State_Strings` sheet at runtime — see Spec v2 §11 for the rule logic.

---

## 3. Screen 1 — Today: Top Header

### Purpose

Above-the-fold orientation. The user lands on Today and within 3 seconds understands what kind of day this is for their skin.

### When it shows

- Default Today lane view
- Every time `/hlhp/scan` returns

### Data sources

- `/hlhp/scan` response — `env_snapshot`, `mood_verdict_today`, `outdoor_ok_score`, `outdoor_ok_band_text`
- Layer 2: `Forecast_Day_Templates` (for the mood headline framing)
- Layer 2: `Lane_State_Strings` (for the "3 alerts ready" + "Sudden event detected" status pills)

### Layout — desktop

```
┌─ Top Header card ────────────────────────────────────────────────────┐
│                                                                      │
│  📍 Vikhroli West, Mumbai · 19 Jun 2026          [UV 6.2] [33.4°C]    │
│                                                  [AQI 73] [RH 59%]   │
│                                                                      │
│  Today is a sebum-rush day.                                          │
│  Priya, heat plus muggy air pushes your jawline harder than          │
│  yesterday. Mid-day blot helps; tonight's cleanse matters.           │
│                                                                      │
│  🛡️  3 acne alerts        💧  Monsoon turning on                     │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Content variables

| Variable | Source | Example |
|---|---|---|
| `{city_locality}` | API `env_snapshot.city` | "Vikhroli West, Mumbai" |
| `{date_display}` | Client-side local time | "19 Jun 2026" |
| `{uv}` | API `env_snapshot.uvi` | "UV 6.2" |
| `{temp}` | API `env_snapshot.temp_c` | "33.4°C" |
| `{aqi}` | API `env_snapshot.aqi_cpcb` | "AQI 73" |
| `{rh}` | API `env_snapshot.rh_pct` | "RH 59%" |
| `{mood_headline}` | API `mood_verdict_today` → display map | "Today is a sebum-rush day." |
| `{mood_sub}` | API `forecast_oneliner` for today | "Priya, heat plus muggy air..." |
| `{status_pill_count}` | API `alerts.length` | "3 acne alerts" |
| `{status_pill_sudden}` | Lane_State_Strings lane_state_010 | "Monsoon turning on" |

### Pill color logic

| Parameter | Band | Pill color |
|---|---|---|
| UV | high, very_high, extreme | warn-orange |
| Temp | hot, very_hot | warn-orange |
| Temp | cold, very_cold | coral-red |
| AQI | satisfactory, moderate | violet-purple |
| AQI | poor, very_poor, severe | warn-orange |
| RH | comfortable | mint-green |
| RH | high, very_high | coral-red |
| RH | low, very_low | warn-orange |

### Personalisation

- `{mood_sub}` in Personalised mode includes user's first name and concern-specific framing
- Guest mode strips the name; uses concern-agnostic language

### Edge cases

- **No live env data:** Show last-cached env with a small "Last updated 14 min ago" badge; downgrade pill colors to neutral
- **Mood verdict = easy_day:** Mood-sub reads "Easy day for skin. Routine basics carry it."
- **Guest mode:** Status pill omits "Priya," prefix; reads "Today is a sebum-rush day."

---

## 4. Screen 2 — Today: Skin Friendliness Index + Score Breakdown

### Purpose

Quantified day-read. The SFI score gives the user one number; the breakdown gives them the four contributing factors in plain language.

### When it shows

- Today lane, immediately below the top header
- Tappable to expand into the alerts modal (Screen 3)

### Data sources

- `/hlhp/scan` response — `outdoor_ok_score`, `outdoor_ok_band_text`, `mood_verdict_today`
- Layer 2: `Forecast_Day_Templates` (for the band-specific skin notes)

### Layout

```
┌─ SFI card ─────────────────────────────────────────────────────────┐
│                                                                    │
│  Your skin outlook                                                 │
│                                                                    │
│   ⭕    Priya, sebum will run hot today. A blot habit through      │
│  60/100 the day and a gentle double cleanse tonight really helps.  │
│        A brightening serum on yesterday's marks is what helps      │
│        most.                                                       │
│                                                                    │
│  ─── Score breakdown ───────────────────────────────────────────── │
│                                                                    │
│  ┌─────────────────────┐  ┌─────────────────────┐                  │
│  │ Sun strength        │  │ Heat                │                  │
│  │ Strong              │  │ Hot afternoon       │                  │
│  │ Post-acne marks     │  │ Sebum runs warmer;  │                  │
│  │ darken faster       │  │ jaw and chin shine  │                  │
│  │ without sunscreen.  │  │ by mid-day.         │                  │
│  │ [████████░░] 70%    │  │ [██████░░░░] 65%    │                  │
│  └─────────────────────┘  └─────────────────────┘                  │
│                                                                    │
│  ┌─────────────────────┐  ┌─────────────────────┐                  │
│  │ Air quality         │  │ Air moisture        │                  │
│  │ Mostly clean        │  │ Muggy, rising       │                  │
│  │ Light particulate — │  │ Fungal-acne risk    │                  │
│  │ background pressure.│  │ on chest and back   │                  │
│  │                     │  │ climbs this week.   │                  │
│  │ [██░░░░░░░░] 25%    │  │ [█████░░░░░] 55%    │                  │
│  └─────────────────────┘  └─────────────────────┘                  │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Score ring

- 88px diameter
- Conic-gradient fill: score% blue (`#2864B8`), remainder light gray (`#DCE5F1`)
- Inner white circle 68px with score number + "/100" label

### Score band → outlook text mapping

| Score | Outlook text |
|---|---|
| 80-100 | Easy day to be outside |
| 60-79 | Comfortable with sunscreen |
| 40-59 | Manageable — protect the basics |
| 20-39 | Plan around it — multiple stressors today |
| 0-19 | Hard outdoor day — head-to-toe protection helps most |

### Skin-language band notes

Pulled from `Forecast_Day_Templates` matched by (band combo × concern). The four labels never use technical jargon ("Sun strength" not "UVI", "Air moisture" not "Relative humidity").

### Interaction

- Tap the entire card → expand into Screen 3 (alerts + chips)
- Tap individual band → opens the band's contributing rules explanation

---

## 5. Screen 3 — Today: Three Alerts + Symptom Chips

### Purpose

The actionable content of the Today lane. Three alerts cover the three skin systems today's environment is pushing on, each with the 4-tier hierarchy expanded inline. Symptom chips give the user a fast in to deeper reads.

### When it shows

- Below the SFI breakdown
- Default expanded on initial load
- Collapsible per alert

### Data sources

- `/hlhp/scan` response — `alerts[]` (top 3 fired) and `science_nugget`
- Layer 1: 6 factor sheets (driven by `trigger_matcher`)
- Layer 2: `Science Nuggets` sheet

### Layout

```
┌─ Three alerts card ─────────────────────────────────────────────────┐
│                                                                     │
│  Three alerts for today                                             │
│                                                                     │
│  ╔═════════════════════════════════════════════════════════════╗    │
│  ║ ●1  Sebum-rush day — face will shine through afternoon       ║    │
│  ║                                                              ║    │
│  ║ Heat plus muggy air pushes sebum hard today. A gentle gel   ║    │
│  ║ cleanse this morning, a blot habit through the day...        ║    │
│  ║                                                              ║    │
│  ║ HOW                                                          ║    │
│  ║ Gel cleanser → niacinamide-class brightening serum → ...     ║    │
│  ║                                                              ║    │
│  ║ DID YOU KNOW                                                 ║    │
│  ║ Skin temperature rising by even a couple of degrees...       ║    │
│  ║                                                              ║    │
│  ║ Source · Skin Diseases in Females (Sarkar) Ch. 4 · Sardana   ║    │
│  ╚═════════════════════════════════════════════════════════════╝    │
│                                                                     │
│  ╔═════════════════════════════════════════════════════════════╗    │
│  ║ ●2  Monsoon's turning on — heads up for chest and back       ║    │
│  ║ ... (same 4-tier structure)                                  ║    │
│  ╚═════════════════════════════════════════════════════════════╝    │
│                                                                     │
│  ╔═════════════════════════════════════════════════════════════╗    │
│  ║ ●3  Cortisol's on the menu — short sleep + festival food     ║    │
│  ║ ... (same 4-tier structure)                                  ║    │
│  ╚═════════════════════════════════════════════════════════════╝    │
│                                                                     │
│  ─── Tap what your skin feels ───                                   │
│  [oily*] [shiny*] [breakout*] [congested] [dark spots] [itchy] ...  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

\* Highlighted in peach for the user's captured concern.

### The 4-tier alert structure

Each alert card renders these tiers inline:

| Tier | Workbook column | Display style |
|---|---|---|
| L1 — Title | Engine-generated from `engagement_archetype` + body keyword | Bold heading, 15px |
| L1 — Body | `alert_l1_personalised` or `alert_l1_guest` | 14px body, 30-50 word range |
| L2 — How | `routine_action` + composed phrase | Small label "HOW" + 13px body |
| L3 — Did You Know | `alert_l2_explainer` | Small label "DID YOU KNOW" + 13px body |
| Source | `source_title` + `source_pages` or PMID | 12px italic on dashed top border |

### Alert card background tints

Three distinct tints for visual separation when all three are expanded:

| Position | Background | Border |
|---|---|---|
| Alert 1 | mint-green tint `#E9F4EC` | `#C7E0CE` |
| Alert 2 | info-blue tint `#ECF2FA` | `#C9D9EE` |
| Alert 3 | violet tint `#EFEAF7` | `#D6CAEB` |

The tints don't encode meaning; they aid scanability when stacked.

### Symptom chip strip

20 chips from the symptom keyword vocabulary, ordered:
1. **Highlighted** in peach (`#FBE0CF` / `#9C3E0A`) — chips relevant to user's captured concern. For acne user: oily, shiny, breakout.
2. **Default** in cream — all other chips.

Tap any chip → navigates to Screen 5 (Symptom-Tap Deep-Dive) with the keyword pre-loaded.

### Footer

Snapshot version + last-updated timestamp:
*"Last updated 19 Jun 2026, 15:50 · Snapshot v1.0 · 1,953 cited rules"*

### Edge cases

- **Only 1 or 2 alerts fire:** Render fewer cards; engine guarantees minimum 1 alert when env data is available
- **All-easy day:** Engine surfaces 1 alert + 2 science nuggets in the same 3-slot frame
- **Internal-only rule fires:** Skip; engine never returns these to client (per spec validation gate)

---

## 6. Screen 4 — Your Skin: Concern Deep-Dive

### Purpose

The depth lane. A user with a captured concern (e.g., acne) lands here to see their substantive routine, expectations, and escalation criteria — content that holds across days, not just today.

### When it shows

- User taps "Your skin" lane
- Direct deep link from a notification or an alert "Learn more"

### Data sources

- `/hlhp/concern_deepdive/{concern_id}` — composes from 6 Layer 2 sheets
- Layer 2: `Concern_Pages`, `Concern_Drivers`, `Concern_Routine_Framework`, `Concern_Myths`, `Concern_Timeline`, `Concern_Dermatologist_Triage`
- Layer 2: `Forecast_Day_Templates` (for the 7-day forecast strip)
- Layer 2: `Daily_Nuggets_Rotation` (for today's nugget)

### Layout

```
┌─ Hero card ─────────────────────────────────────────────────────────┐
│ Your skin · Concern deep-dive                                       │
│                                                                     │
│ Your adult acne — sebum patterns, food triggers, post-mark fade     │
│ Adult-onset and adult-female acne specifically. Indian skin patterns│
│ including PIH and hormonal cycle.                                   │
│                                                                     │
│ [Hormone-linked]  [Diet-sensitive]  [PIH-prone]  [Manageable]       │
└─────────────────────────────────────────────────────────────────────┘

┌─ Routine framework ─────────────────────────────────────────────────┐
│ ─── Your routine framework ───                                      │
│                                                                     │
│  ☀ Morning                       🌙 Evening                         │
│  1. A gentle gel cleanser        1. An oil cleanse then gel ...      │
│  2. A brightening serum to ...   2. A BHA serum 2-3 nights ...      │
│  3. An oil-free non-comedogenic  3. A retinoid at night, built up.. │
│     moisturizer.                 4. A lightweight hydrating gel...  │
│  4. A non-comedogenic sunscreen.                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─ Week ahead ────────────────────────────────────────────────────────┐
│ ─── How's your week going to be ───                                 │
│                                                                     │
│  Today    [60]  Sebum-rush day. Blot + cleanse helps.   ← today     │
│  Tomorrow [62]  Sebum-rush continuing — keep the rhythm             │
│  Sat      [55]  Heat + humidity stacking                            │
│  Sun      [50]  First monsoon shower likely                         │
│  Mon      [58]  Monsoon onset. Lighter scalp oil this week          │
│  Tue      [62]  Cooler and humid                                    │
│  Wed      [65]  Steady humid week ahead                             │
└─────────────────────────────────────────────────────────────────────┘

┌─ Dermatologist triage ──────────────────────────────────────────────┐
│ ─── When to see a dermatologist ───                                 │
│                                                                     │
│ ┃ Worth a consult if:                                               │
│ ┃ • Nodular or cystic acne, especially along the jawline.           │
│ ┃ • Acne with irregular menstruation, facial hair, hair shedding.   │
│ ┃ • Considering isotretinoin or hormonal acne management.           │
│ ┃ • Severe post-acne pigmentation or scarring causing distress.     │
└─────────────────────────────────────────────────────────────────────┘

┌─ Did you know ──────────────────────────────────────────────────────┐
│ ─── Did you know ───                                                │
│                                                                     │
│ ┃ TODAY'S FACT             1 new fact every day                     │
│ ┃                                                                   │
│ ┃ Adult female acne represents about two-thirds of acne dermatology │
│ ┃ visits in India. It can continue from teens into menopause — not  │
│ ┃ 'left over' from adolescence...                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Section ordering

Per `HLHP_Composition_Layer_Schema.md`, the deep-dive renders in this fixed order:

1. **Hero** — Concern_Pages title + sub + 4 mood pills
2. **Today's read** — small embedded strip showing how today's env is touching this concern
3. **Routine framework** — AM + PM step lists from Concern_Routine_Framework
4. **Week ahead** — 7-day forecast strip from Forecast_Day_Templates
5. **Dermatologist triage** — escalation criteria from Concern_Dermatologist_Triage (left-coral-border panel)
6. **Did You Know** — today's rotation from Daily_Nuggets_Rotation (left-violet-border panel)

### Optional sections (collapsible "Learn more")

- **Drivers** — Concern_Drivers cards (5 per concern)
- **Myths** — Concern_Myths corrections (4 per concern)
- **Timeline** — Concern_Timeline phases (4 per concern)

These can sit one tap deeper as "Learn more about your acne" expandable panel — accessible but not visually overwhelming on first read.

### Week ahead row visual treatment

| Element | Style |
|---|---|
| Today row | Coral background `#FCEDED` border `#F4CFCF` |
| Other rows | White background |
| Date column | 12px label + 11px muted day name |
| SFI column | 14px bold in cream pill `#F5E8D2` |
| Text column | 13px body |

### Personalisation

- Hero sub-line in Personalised mode references user's name in subtle places
- Routine framework filters by user's `skin_type` variant where applicable
- Today's nugget rotation tracks per `user_id` for 30-day no-repeat
- Guest mode: same structure, generic framing, no name

### Edge cases

- **No captured concern:** Show concern selection screen first
- **Multi-concern user (acne + melasma):** Tab switcher at top to flip between deep-dives
- **Forecast unavailable:** Hide week-ahead section; show "Forecast temporarily unavailable" placeholder

---

## 7. Screen 5 — Symptom-Tap Deep-Dive

### Purpose

When a user taps a symptom chip from anywhere in the app, they land on a 4-section explainer page that tells them why, what to do now, and when to escalate.

### When it shows

- From the chip strip on Screen 3
- From the persistent top-bar chip strip (desktop)
- From the bottom-bar FAB (mobile)
- From Explore lane "Browse by what you're feeling" tiles

### Data sources

- `/hlhp/symptom_explainer/{symptom_keyword}` — composes from Symptom_Explainer_Pages
- API also injects today's env snapshot for contextual today-strip
- Related symptoms from a small `symptom_relations` map (engineer-side config)

### Layout

```
┌─ Hero card ─────────────────────────────────────────────────────────┐
│ ← Back to Today                                                     │
│                                                                     │
│ SYMPTOM-TAP DEEP-DIVE                                               │
│                                                                     │
│ 👆 You tapped: oily                              ┌──────────────┐   │
│                                                  │              │   │
│ Why your skin feels oily right now               │   💧          │   │
│ A 4-section read on what's driving it, what     │              │   │
│ helps in the moment, and when this stops being   └──────────────┘   │
│ something a routine alone can fix.                                  │
│                                                                     │
│ ┃ Today in Mumbai · 19 Jun · Heat is in the hot band and humidity   │
│ ┃ is rising. The mix is pushing your sebum harder than yesterday... │
└─────────────────────────────────────────────────────────────────────┘

┌─ The 4 sections card ───────────────────────────────────────────────┐
│ THE 4 SECTIONS · IN ORDER                                           │
│                                                                     │
│ ╔══ ●1 Why this happens (blue tint) ════════════════════════════╗    │
│ ║ Sebaceous glands respond to androgens. Hot humid weather...   ║    │
│ ║ Source · Skin Diseases in Females Ch. 4 · PMID 38605790       ║    │
│ ╚═══════════════════════════════════════════════════════════════╝    │
│                                                                     │
│ ╔══ ●2 Common patterns (mint tint) ═════════════════════════════╗    │
│ ║ T-zone shine within hours of cleansing. Mid-day shine across..║    │
│ ║ Source · Humidity:187 · Lifestyle:171 · Sardana CBS p. 343    ║    │
│ ╚═══════════════════════════════════════════════════════════════╝    │
│                                                                     │
│ ╔══ ●3 What helps now (lavender tint) ══════════════════════════╗    │
│ ║ A gentle gel cleanser twice a day, a niacinamide-class...     ║    │
│ ║ ⚡ These four steps are already in your routine framework.    ║    │
│ ║ Source · UV:558 · UV:582 · Cosmetic Derm SoC (Alam)           ║    │
│ ╚═══════════════════════════════════════════════════════════════╝    │
│                                                                     │
│ ╔══ ●4 When to escalate (coral tint) ═══════════════════════════╗    │
│ ║ Oily skin with persistent acne despite three months...        ║    │
│ ║ Source · Lifestyle:191 · Lifestyle:215 · PMID 29156452        ║    │
│ ╚═══════════════════════════════════════════════════════════════╝    │
└─────────────────────────────────────────────────────────────────────┘

┌─ Related + CTA card ────────────────────────────────────────────────┐
│ ─── Related symptoms — same family ───                              │
│                                                                     │
│  [shiny]      The look of the oil      →                            │
│  [breakout]   When oil tips into acne  →                            │
│  [congested]  Pore blockage layer      →                            │
│  [dark spots] What's left behind       →                            │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────┐         │
│ │ Open your Adult Acne deep-dive                       →  │         │
│ │ Drivers · routine · week ahead · today's nugget         │         │
│ └─────────────────────────────────────────────────────────┘         │
│                                                                     │
│         Last updated 19 Jun 2026, 15:50 · Symptom Explainer v1.0    │
└─────────────────────────────────────────────────────────────────────┘
```

### Section tint logic

Each of the 4 sections has a distinct background tint to aid scanning:

| Section | Background tint |
|---|---|
| 1 Why this happens | info-blue `#ECF2FA` |
| 2 Common patterns | mint-green `#E9F4EC` |
| 3 What helps now | violet-purple `#EFEAF7` |
| 4 When to escalate | coral-red `#FCEDED` |

### Today's environment strip

Above the four sections, a small blue-tinted strip ties the explanation to the user's current context:
- Renders `Today in {city} · {date} · {one-line env description tied to symptom}`
- For "oily" today: heat + RH rising context
- For "tight" in winter: low RH + heated indoor air context
- Pulled by composing env_snapshot bands with a small symptom×context lookup table

### Related symptoms

A small static `symptom_relations` map maintained engineer-side:

```python
SYMPTOM_RELATIONS = {
    "oily": ["shiny", "breakout", "congested", "dark_spots"],
    "tight": ["dry", "flaky", "stinging"],
    "itchy": ["red", "flaky", "scalp_itch"],
    "dark_spots": ["tan", "dull", "breakout"],
    # ... 20 entries
}
```

Each related chip shows the chip name + a 4-word context cue.

### CTA — Open your concern deep-dive

Dark navy button linking to Screen 4 for the user's captured concern. If multiple concerns, link to the most relevant one for this symptom (engine-side decision).

### Edge cases

- **Symptom not in vocabulary:** Should not happen if chip strip is correct; defensive fallback shows "Sorry, no explainer yet"
- **Guest mode with no concern:** Hide the concern-deep-dive CTA, show "Set up your skin profile" CTA instead
- **Environment data stale:** Hide today's-context strip; show only the 4 sections

---

## 8. Screen 6 — Explore Lane

### Purpose

A curiosity-driven browse experience. Users come here when they don't have a specific question — to read, to plan ahead, or to learn something new.

### When it shows

- Tap "Explore" lane in nav

### Data sources

- `/hlhp/explore?user_id={uuid}&city=Mumbai` — composed response
- Layer 2: `Event_Guides` filtered by city + month_window + 30-day proximity
- Layer 2: `Daily_Nuggets_Rotation` (for science feed swipe)
- Layer 2: `Lane_State_Strings.lane_state_026` (for "Up next" strip)
- 20-symptom keyword list

### Layout

```
┌─ Explore lane card ─────────────────────────────────────────────────┐
│ LANE · EXPLORE                                                      │
│ 🧭 Explore                                                          │
│ Event guides · science feed · symptom browse                        │
│                                                                     │
│ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓     │
│ ┃ ⏰ Monsoon onset is up next                                  ┃     │
│ ┃ Mumbai · 3-4 days away                                  →    ┃     │
│ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛     │
│                                                                     │
│ ─── Event guides for your city + dates ───                          │
│                                                                     │
│ 🌧️  HAPPENING THIS WEEK · 4 MIN READ                                │
│     Monsoon onset — your skin's first humid week                    │
│     Fungal acne on chest and back · hair oil heaviness...           │
│                                                                     │
│ 🎒  WITHIN 2 WEEKS · 6 MIN READ                                     │
│     School reopens in monsoon — for teens and their skin            │
│     Adolescent acne flare cluster · shared towels...                │
│                                                                     │
│ 🍳  FOR LATER · 5 MIN READ                                          │
│     Festival cooking marathon — your skin's heat response plan      │
│     Diwali sweets · Eid biryani · long hours over hot oil...        │
│                                                                     │
│ 🏖️  PLAN AHEAD · 5 MIN READ                                         │
│     Beach vacation — what your skin will go through and how to prep │
│     Pre-trip prep · in-trip protection · post-trip recovery...      │
│                                                                     │
│         📋 Browse all 12 guides                                      │
│                                                                     │
│ ─── Science feed — today's nugget ───                               │
│                                                                     │
│ ┃ SKIN SCIENCE                          ← 3 of 182 →                │
│ ┃                                                                   │
│ ┃ Adult female acne represents about two-thirds of acne dermatology │
│ ┃ visits in India. It can continue from teens into menopause...     │
│ ┃                                                                   │
│ ┃             ○  ○  ●  ○  ○                                         │
│                                                                     │
│ ─── Browse by what you're feeling ───                               │
│                                                                     │
│ [oily*] [shiny*] [breakout*] [tight] [dry]                          │
│ [flaky] [dull] [red] [sensitive] [stinging]                         │
│ [tingling] [itchy] [puffy] [tired_eyes] [dark_spots]                │
│ [tan] [rough] [congested] [hair_shedding] [scalp_itch]              │
└─────────────────────────────────────────────────────────────────────┘
```

### Event guide ranking

Engine-side, the event guides are ranked by:

1. **Proximity** — guides whose `month_window` overlaps the next 7 days come first
2. **City match** — guides whose `city_scope` matches user's city or `pan_india`
3. **Concern relevance** — guides matching captured concern get a small priority boost

Maximum 4 guides shown by default; "Browse all" exposes the full 12.

### Time-relevance meta tags

| Window | Tag display |
|---|---|
| Within 0-7 days | HAPPENING THIS WEEK |
| Within 8-14 days | WITHIN 2 WEEKS |
| Within 15-60 days | FOR LATER |
| Beyond 60 days | PLAN AHEAD |

### Science feed nugget pagination

- Single-card view with `← N of 182 →` navigator
- 5-dot indicator below for visual position (resets every 5 nuggets)
- Engine respects per-user 30-day no-repeat window
- Category badge in top-left: skin_science / mechanism / indian_culture / mythbust

### Symptom browse grid

5 columns × 4 rows = 20 keywords. User's concern-relevant chips highlighted in peach. Tap any → Screen 5.

### Edge cases

- **No upcoming events for user's city:** Up-next strip hides; engine shows nearest event in calendar
- **No nuggets available:** Should not happen given 182-row pool with 30-day rotation; defensive fallback shows "More nuggets coming"

---

## 9. Screen 7 — History Lane

### Purpose

Returning user experience. Shows what changed in the last 30 days, especially what the user missed if they've been away.

### When it shows

- Tap "History" lane in nav
- Banner override fires on first open after >14 day gap

### Data sources

- `/hlhp/history?user_id={uuid}&days=30` — composed response
- Postgres `scan_log` table (for SFI trend + most-fired mood)
- New `sudden_event_log` table (for Δ-detector firings)
- Engine-side computation of "most-fired mood verdict over period"

### Layout

```
┌─ History lane card ─────────────────────────────────────────────────┐
│ LANE · HISTORY · RETURNING AFTER 14 DAYS AWAY                       │
│ 🕐 History                                                          │
│ SFI trend · sudden events · what you missed                         │
│                                                                     │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │ ⓟⓥ  Welcome back, Priya. While you were away, Mumbai had a    │  │
│ │      heavier-than-usual humidity stretch and your skin         │  │
│ │      probably noticed.                                         │  │
│ │      Last opened 14 days ago · catching you up on the last 30  │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐                   │
│  │ Sudden events       │  │ SFI average         │                   │
│  │   3                 │  │   61                │                   │
│  │ Caught by your Δ-   │  │ Last 30 days · ↓    │                   │
│  │ detector last 30 d. │  │ from 68 prior month │                   │
│  └─────────────────────┘  └─────────────────────┘                   │
│                                                                     │
│ ┌── SFI trend · last 30 days ──────────────────────────────────┐    │
│ │  100│                                                        │    │
│ │     │\___/\__                                                │    │
│ │     │       \__   __                                         │    │
│ │     │          \_/  \_/\__   ___ ●     ___                   │    │
│ │     │                  ●   \/    \___/   \                   │    │
│ │     │                                ●                       │    │
│ │   0 │_________________________________________________       │    │
│ │       Mumbai · acne lens         (● = sudden events)         │    │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ─── Sudden events while you were away ───                           │
│                                                                     │
│ 8 Jun · 11 days ago    🔥  Heat wave surge — temp jumped to hot     │
│                            Sebum-rush conditions · acne flare-prone │
│                                                                     │
│ 14 Jun · 5 days ago    💧  Humidity surge — RH jumped 25 pts in 48h │
│                            Pre-monsoon signal · fungal acne window  │
│                                                                     │
│ 17 Jun · 2 days ago    🌧  First monsoon-pattern day — transition   │
│                            Routine adjustment recommended           │
│                                                                     │
│ ─── Most-fired alert this month ───                                 │
│                                                                     │
│ 12 days out of 30  🔥  Sebum-rush day                               │
│                        Your most common mood verdict — pattern      │
│                                                                     │
│ ┌─────────────────────────────────────────────────────────────┐     │
│ │  Read your 2-minute catch-up                            →    │     │
│ │  A summary written specifically for someone returning today  │     │
│ └─────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### Returner banner

Triggered by `Lane_State_Strings.lane_state_034` (returning after >14 days). Includes:
- User initials avatar in lemon-green
- Warm headline ("Welcome back, Priya")
- One-line context about what happened in their city
- Last-opened timestamp

### Stat grid

2 KPI cards at the top:
- **Sudden events** — count from `sudden_event_log`
- **SFI average** — computed from `scan_log` over the period, with delta vs prior month

### SFI trend chart

- SVG sparkline, 30 data points
- Blue gradient fill below the line
- Reference dashed grid lines at 30 and 60
- Red dots marking days where sudden_event_log fired
- Header includes city + concern context ("Mumbai · acne lens")

### Event log

Three most-recent sudden events (or all if ≤5):
- Date column with "N days ago" relative time
- Icon colored by event type (heat = peach, humidity = blue, transition = coral)
- Two-line description: event headline + skin-impact note

### Most-fired alert insight

Shows the user's most common mood verdict over the 30-day window. Insight framing:
*"Your most common mood verdict — pattern worth knowing"*
This is the *retrospective insight* layer — surfaces patterns the user might not have noticed.

### Catch-up CTA

Dark navy button at the bottom. Triggers a new modal/page with a 2-minute composed narrative:
- Composes from sudden_event_log + SFI trend + most-fired mood
- Template-based (no LLM call); pulls phrases from a small library
- Stitched into 3-4 short paragraphs covering: what happened, what your skin probably felt, what to focus on this week

### Edge cases

- **Returning after <14 days:** Banner doesn't show; lane defaults to last-30-days summary view
- **First-time History visit (≤7 days of history):** Show "Building your history — check back in a week" placeholder
- **No sudden events in period:** Event log section shows "Quiet month for your city — your routine carried it"

---

## 10. API contract summary

| Endpoint | Method | Used by Screen | Cache TTL |
|---|---|---|---|
| `/hlhp/scan` | POST | 1, 2, 3 | 30 min per (user, 30-min window) |
| `/hlhp/symptom_tap` | POST | 5 (legacy) | — |
| `/hlhp/symptom_explainer/{keyword}` | GET | 5 | 24 hr per (keyword, concern, city, hour) |
| `/hlhp/concern_deepdive/{concern_id}` | GET | 4 | 24 hr per (concern, user) |
| `/hlhp/event_guides` | GET | 6 | 6 hr per (city) |
| `/hlhp/explore` | GET | 6 | 6 hr per (user) |
| `/hlhp/week_ahead` | GET | 2 (forecast), 4 | 6 hr per (user, city) |
| `/hlhp/history` | GET | 7 | 1 hr per (user) |
| `/hlhp/catchup` | GET | 7 (CTA target) | Invalidates on next scan |
| `/hlhp/consent` | POST | (settings) | — |
| `/hlhp/health` | GET | (monitoring) | — |

Total: 11 endpoints. The first 8 drive user-facing screens; the last 3 are settings/monitoring.

---

## 11. Empty / edge / error states

| State | Behavior |
|---|---|
| **First-time visitor, no profile** | Land on consent + 8-field profile setup flow before Today |
| **Guest mode (consented to env logging only)** | All screens render with `alert_l1_guest` columns; no name, no concern-specific Your Skin lane |
| **Live env feed down** | Show last-cached env with "Last updated N min ago" badge; if cache expired, show "Skin friendliness data temporarily unavailable" placeholder |
| **Snapshot mismatch** | Force refresh; engine returns 503 if snapshot version mismatch detected |
| **Empty captured concern** | Your Skin lane shows "Set up your skin profile" CTA |
| **Symptom keyword without explainer** | Defensive fallback: "We're still writing this explainer. Tap a related symptom." |
| **No event guides for city** | Up-next strip hides; show nearest pan-India guide |
| **Returning user, no history yet** | Show "Building your history — check back in a week" |
| **Network offline** | Show last cached scan response; "Offline — reconnect to refresh" banner |

---

## 12. Guest mode vs Personalised mode rendering

| Element | Guest | Personalised |
|---|---|---|
| Top header mood-sub | "Today is a sebum-rush day. Heat plus muggy air pushes sebum hard." | "Priya, heat plus muggy air pushes your jawline harder than yesterday." |
| Alert L1 column | `alert_l1_guest` | `alert_l1_personalised` |
| SFI outlook | Generic indicative voice | Includes user name + concern reference |
| Your Skin lane | Shows "Set up your skin profile" CTA | Shows full Concern Deep-Dive |
| Daily Nuggets | Universal + concern-agnostic | 30-day no-repeat per user_id |
| Symptom chips | All 20 cream-colored | Concern-relevant chips highlighted in peach |
| History lane | Last 30 days of scan_log | Plus returner banner if >14 days away |
| Coach voice (Phase 2) | Not available | Available with streak + name + continuity |

Guest mode is fully functional — never block the user from value because they haven't given consent yet.

---

## 13. Phase 1 vs Phase 2 differences

### Phase 1 (launch)

All 7 screens render. Personalised mode uses `alert_l1_personalised` columns directly from the workbook (no name interpolation). Daily Nuggets rotate with 30-day no-repeat per user. Sudden-event detection fires. Festival overlay and city seasonal transitions live.

### Phase 2 additions

| Surface change | Phase 2 enhancement |
|---|---|
| Top header mood-sub | Coach voice template with name + streak: *"Priya, 21 days of sebum control. The shine today isn't backsliding — it's the air."* |
| Alert L1 body | Coach-voice modulation based on streak: *"Heat plus muggy air today, Priya. You've held the routine for 3 weeks — keep going."* |
| Your Skin lane — new Streak Counter card | Shows per-routine_action streak counts (sunscreen streak, cleansing streak, sebum-control streak) |
| Your Skin lane — new "Tomorrow looks like…" card | Pulls forecast_fetcher data, surfaces tomorrow's mood verdict + recommended prep |
| History lane | Adds "Action log" section — logs of which alerts were acted upon vs dismissed |

Engine-side, Phase 2 introduces:
- `user_state` table
- `streak_engine` module
- `rotation_engine` (avoids repeating archetype clusters back-to-back)
- `coach_template_assembler` (composes from the 80 authored Coach_Voice_Templates)
- `voice_modulator` (adjusts strength language by streak)
- `forecast_fetcher`

Phase 2 ships incrementally. No screen redesign needed — same templates, voice modulator wraps the text at render time.

---

## 14. Implementation checklist for frontend

### Component library

Build these primitives first:

- [ ] `SectionCard` — cream-bg outer wrapper with optional title underline
- [ ] `InnerCard` — white-bg with subtle border
- [ ] `LeftAccentPanel` — colored 3px left border for emphasis panels
- [ ] `Pill` — semantic colored badge variants
- [ ] `MoodHeadline` — 22px indicative voice headline
- [ ] `ScoreRing` — 88px SVG conic gradient ring with inner score
- [ ] `BandCard` — 4-panel score breakdown card with progress bar
- [ ] `AlertCard` — 4-tier expandable alert with tinted backgrounds
- [ ] `Chip` — symptom keyword chip with selected/default/highlighted states
- [ ] `WeekAheadRow` — date-SFI-text row with today highlight
- [ ] `TriagePanel` — coral-bordered escalation list
- [ ] `NuggetCard` — violet-bordered swipeable card
- [ ] `EventGuideCard` — icon + meta + title + sub
- [ ] `EventLogRow` — date + icon + 2-line description
- [ ] `TrendChart` — SVG sparkline with reference lines and event dots
- [ ] `LaneNav` — top horizontal nav (desktop) + bottom tab bar (mobile)
- [ ] `SymptomFAB` — center-floating action button (mobile)

### Page assemblies

- [ ] Today page — composed of Top Header + SFI Modal + Three Alerts + Chip Strip
- [ ] Your Skin page — Concern Deep-Dive routing per `concern_id`
- [ ] Symptom-Tap page — 4-section deep-dive routing per `symptom_keyword`
- [ ] Explore page — Event guides + Science feed + Symptom browse
- [ ] History page — Returner banner (conditional) + Stat grid + Trend chart + Event log + Catch-up CTA

### State management

- Use React Query or SWR for API caching aligned with the TTLs in §10
- Persist user's last-viewed lane in localStorage
- Snapshot version stamped on every API response — show warning banner if it changes mid-session

### Accessibility

- Every Screen must have a visually-hidden h1 summarizing the screen for screen readers
- Color contrast minimum 4.5:1 for body text on backgrounds; verified for all tint pairs
- All interactive cards have keyboard navigation (Tab + Enter)
- Symptom chip strip is fully keyboard navigable

### Performance

- Target p95 first-paint < 1.5 seconds
- Lazy-load Explore and History lanes (not needed on first Today scan)
- Defer event guide images (if any) below the fold
- Preload `/hlhp/concern_deepdive/{user_concern}` on Today lane open

### Snapshot version handling

The API stamps `snapshot_version` on every response. If the version changes between requests within a session:
- Surface a small "App updated — refreshing your data" toast
- Re-fetch all open lane responses
- Don't break the user out of their current view

---

## Appendix A — Visual mockups reference

Interactive HTML mockups of each screen were rendered during the design phase and are available on request. Key screen renders:

| Screen | Reference filename |
|---|---|
| Screen 1-3 (Today triplet, acne user) | `hlhp_acne_user_screens.html` (rendered widget) |
| Screen 1-3 (Today triplet, melasma user) | `hlhp_three_screens_refined.html` |
| Screen 4 (Concern Deep-Dive, melasma) | `hlhp_concern_deepdive_melasma.html` |
| Screen 5 (Symptom-Tap Deep-Dive, "oily") | `hlhp_symptom_tap_oily.html` |
| Screen 6 + 7 (Explore + History) | `hlhp_explore_and_history_lanes.html` |
| Navigation chrome | `hlhp_navigation_chrome.html` |
| Redesigned versions vs reference live screens | `hlhp_redesign_v2.html` |

When a designer formalises these in Figma, the artboards should match the layouts in this document. Once Figma is live, this Appendix gets updated with frame links.

---

## Appendix B — Workbook column → UI surface map

| Workbook column | UI surface | Notes |
|---|---|---|
| `alert_l1_personalised` | Screen 3 Alert body (Personalised) | Indicative voice locked |
| `alert_l1_guest` | Screen 3 Alert body (Guest) | Same content, generic framing |
| `alert_l1_evening_personalised` | Screen 3 Alert body (PM phase, Personalised) | Renders 16:00-03:59 local |
| `alert_l1_evening_guest` | Screen 3 Alert body (PM phase, Guest) | Same time window |
| `alert_l2_explainer` | Screen 3 "DID YOU KNOW" tier | 50-90 words |
| `mood_verdict_tag` | Screen 1 Mood headline mapping | 10-tag vocabulary |
| `engagement_archetype` | Internal — drives ranker diversity | Not visible |
| `physical_analogy` | Optional in Screen 3 alert body | ≤20 words |
| `body_sensation_decode` | Screen 5 "Common patterns" body | ≤30 words |
| `symptom_keyword` | Screen 3 chip + Screen 5 routing | 20-keyword vocabulary |
| `routine_action` | Screen 3 "HOW" tier + icon | 21-action vocabulary |
| `visual_icon_hint` | Screen 3 alert icon | 18-icon vocabulary mapped to Tabler |
| `Concern_Pages.hero_title` | Screen 4 hero title | Single per concern |
| `Concern_Drivers.driver_*` | Screen 4 "Learn more — Drivers" panel | 5 per concern |
| `Concern_Routine_Framework.step_text` | Screen 4 Routine framework | 8 per concern (AM+PM) |
| `Concern_Myths.myth_correction` | Screen 4 "Learn more — Myths" panel | 4 per concern |
| `Concern_Timeline.phase_expectation` | Screen 4 "Learn more — Timeline" panel | 4 per concern |
| `Concern_Dermatologist_Triage.escalation_trigger` | Screen 4 Triage panel + Screen 5 Section 4 | 3-5 per concern |
| `Event_Guides.section_body` | Screen 6 Event guide content | 4-5 sections per guide |
| `Symptom_Explainer_Pages.section_body` | Screen 5 Section 1-4 bodies | 4 sections per keyword |
| `Daily_Nuggets_Rotation.nugget_text` | Screen 4 + Screen 6 nugget card | 30-day no-repeat per user |
| `Forecast_Day_Templates.forecast_one_liner` | Screen 4 Week-ahead rows + Screen 2 mood-sub | Matched by band combo + concern |
| `Lane_State_Strings.cta_text` | Lane nav subtitle + Up-next strip | Highest-priority match wins |
| `source_workbook_rows` | Screen 3 + 4 + 5 source line | Audit trail to Layer 1 |

---

## Appendix C — Glossary

| Term | Definition |
|---|---|
| Layer 1 | The 1,953 dermatology-cited rows in the 6 factor sheets — the evidence spine |
| Layer 2 | The 828 authored composition rows in the 11 user-surface sheets |
| Snapshot | An immutable build artifact of the workbook, versioned by content hash |
| Mood verdict | One of 10 day-tags shaping the headline framing |
| SFI | Skin Friendliness Index — composite 0-100 environmental score |
| Δ-detector | Sliding-window check that fires sudden-event tags when env swings |
| Festival overlay | Calendar JSON mapping Indian festivals → community anchor tags |
| Lane | One of 4 top-level navigation areas (Today / Your Skin / Explore / History) |
| Symptom-tap | The 20-keyword chip flow that opens 4-section deep-dive pages |
| Phase 1 | Launch — rule-matching, L1/L2, all 7 screens render |
| Phase 2 | Coach voice — name + streak + continuity wired in over the same templates |

---

**End of UI Screen Specifications v1.0.**

Questions, design feedback, implementation notes: marathe.ajit@gmail.com
