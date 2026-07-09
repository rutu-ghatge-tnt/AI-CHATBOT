# HLHP Screen Frames — Figma Layout Spec

All frames are 420 × 720 px (iPhone-ish portrait), positioned in a 4-column grid on the **Screens** page with 80px gutters.

Frame outer styling (all 9 frames):
- Background: `{semantic.background.frame}` (`#FBF4E8`)
- Radius: `{core.radius.xl}` (28px)
- Shadow: `{core.shadow.frame-outer}`

---

## Frame layout per screen (top → bottom)

Every screen shares this vertical stack:

1. **Toolbar** (44 px) — brand left, sound toggle right, 0.5 px bottom line
2. **Tab strip** (52 px) — 8 tabs, 0.5 px bottom line, scrollable overflow
3. **Badge strip** (44 px) — "EARNED" label + 4 earned + 3 locked badges, soft indigo wash background
4. **Coach bubble** (auto-height, ~58 px) — indigo gradient pill, 14 px outer margin
5. **Screen content** (auto-fill, ~520 px) — varies by tab
6. **Optional share row** (only on Share tab, 56 px)

---

## Frame 0 — Onboarding Overlay

**Dimensions:** 420 × 720 (full overlay)
**Background:** rgba(26, 43, 71, 0.96)
**Position:** Stacked behind all other frames with z-index, or shown as a separate frame for spec purposes.

**Content (centred vertically):**
- Mascot 140×160 (bobble animation marker)
- 16 px gap
- "Meet your skin coach" — h2-section style, white, centred
- 6 px gap
- Sub-line: "I learn your skin's patterns across humidity, UV, sleep, and pollution — then quietly tell you what to do, only when it actually matters." — body style, white at 0.8 alpha, centred, max-width 280
- 20 px gap
- "Let's begin" CTA — gold-bright background, ink-deep text, padding 12×28, radius round
- 10 px gap
- "Skip for now" — micro text, white at 0.5 alpha, underline-on-hover

---

## Frame 1 — Hello

**Background gradient:** linear `{semantic.verdict.warm-day}` → `{semantic.verdict.celebration}` → transparent
**Background animation marker:** bgBreathe 8s

**Top-right:** Sun SVG (60×60), sunRotate 28s marker
**Mid-area, behind content:** Cloud SVG 70×36, cloudDrift 30s marker (2 instances offset)

**Centre stack:**
- "Baner · 23 June" — micro-label muted
- 4 px gap
- "Good morning, Ajit" — h1-greeting (typewriter animation marker)
- 20 px gap
- **MoodOrb** component, centred
- 10 px gap
- "Your skin's feeling **summer-warm** today" — body style, ink-mid, "summer-warm" tinted amber-warm
- 16 px gap
- **CTAButton/primary** — "Check in for today" with hand-pointing icon, pulseGlow shadow at rest

---

## Frame 2 — Log

**Background:** ellipse-at-top radial overlay in `{semantic.verdict.humidity}` at 8% alpha
**Particles:** 10 humidity droplets, drift animation marker

**Content:**
- replay-bar with "How does your skin feel?" label + replay icon
- 14 px gap
- **Chip cluster:** 7 chips horizontal-wrap (breakout, itchy, dry, tight, red, oily, dull)
- 14 px gap
- **Follow-up card** (step2) — auto-shown when chip tapped, label "Where on your face?" + 4 location chips
- 14 px gap
- **Follow-up card** (step3) — "How many new ones today?" + 4 count buttons (1, 2-3, 4-6, 7+)
- 14 px gap
- **Captured-data card** (light-indigo background) — 4 rows: Symptom / Location / Count / Environment
- 14 px gap
- **Final card** (step4) — "Your engine learned something new" with sparkle icon

---

## Frame 3 — Streak

**Background:** ellipse-at-top radial in `{core.colour.amber-light}` at 20% alpha
**Particles:** 16 embers rising from base of flame

**Content:**
- replay-bar "Day 23 streak"
- **Flame group:** 150×188 stacked SVG layers (orange outer, amber mid, gold inner), flameFlicker marker
- **Glow ring:** radial behind flame, ringPulse marker
- **Number "23":** white digits with text-shadow, centred inside flame
- "days strong" caption below
- 18 px gap
- **Day grid:** 7 columns × 1 row of DayDot components (M/T/W/T/F/S/S); 4 done, 1 today, 2 pending
- 16 px gap
- **Milestone card** with shimmer marker: trophy icon + "7 days to your 30-day badge" + "Only 3% of users reach this"

---

## Frame 4 — Surge

**Background:** ellipse-at-top radial in `{semantic.verdict.surge-alert}` at 12% alpha
**Background animation:** bgBreathe 4s (faster — urgent)
**Particles:** 14 amber heat motes

**Content:**
- replay-bar "Sudden event detected"
- **Push banner** (positioned absolute, top 70 px): white card, red-pale border, alert-glow shadow, slideDown marker
  - Inside: 32×32 amber-pale icon tile + content (label "HEAT SURGE IN PUNE" red-alert + 6px pulsing dot + "SFI dropped from 78 to 54 in 3 hours" + meta "UV peaked at 11.2 · feels-like 41°C")
- 120 px reserved space for push to clear
- **ScoreRing** 130×130, value 78 (becomes 54 after dip animation)
- 12 px gap
- **Mascot/worried** 80×100
- 4 px gap
- "Your skin will feel this. Stay shaded between 11 and 4." — body caption
- 12 px gap
- **Spike chart:** 8 bars, scaleY animation marker, red gradient (bars 5–6 highest as the surge peak)
- 3 px gap
- Hour labels: "9am · noon · 3pm" between justified

---

## Frame 5 — Recap

**Background:** linear-gradient amber-light → indigo-primary at low alpha
**Background animation:** bgBreathe 10s

**Content:**
- replay-bar "June at a glance"
- Centred header: "Your June" label + "30 days · 1 surge · streak intact"
- 14 px gap
- **Track row** (80 px):
  - Day line strip: 30 day-marks (4 px each, gap 3 px), env-coloured per day (green-leaf for calm, amber for warm, red for surge day, indigo for humid days, indigo-deep for surge cluster)
  - Walker mascot (30×38), positioned bottom-left at start, animates left-to-right over 8s
- 8 px gap each:
  - **Callout 1** — sun-high icon: "**June 12** · Heat surge — SFI 78 → 54 · you handled it"
  - **Callout 2** — droplet icon: "**June 19** · Humidity wave — barrier-stress mood for 4 days"
  - **Callout 3** — flame icon: "**June 23** · Day 23 of your streak — keep it lit"
- 10 px gap
- **Stamp card** (ink-deep background, cream text): "YOUR JUNE VERDICT" label gold + "Stronger than May" + "Avg SFI 68 (was 61) · 0 dropped days" + "Share" pill top-right

---

## Frame 6 — Patterns

**Background:** ellipse-at-top radial in `{semantic.verdict.barrier-stress}` at 8% alpha
**Particles:** 8 purple idea-motes drift upward

**Content:**
- replay-bar "Your skin patterns"
- **Insight hero** (indigo gradient card): "WE NOTICED" label + "3 patterns in your last 47 logs" + bulb icon
- 10 px gap
- **Pattern card 1:** ribbon "83% match" + headline "Itchy days cluster on high-humidity afternoons" + 30-dot pattern timeline + correlation bar fills to 83% + body text + "Alert on humidity surge" CTA in indigo
- 10 px gap
- **Pattern card 2:** ribbon green "71% match" + headline "Best window: weekends at home" + 7-cell week grid (weekends green, weekdays neutral) + body + "Set weekday sleep reminder" CTA in green-deep
- 10 px gap
- **Pattern card 3:** ribbon amber-red "68% match" + headline "Morning dust hits harder than afternoon UV" + 12-bar hour chart (9–10am bars red as spike) + body + "Plan a morning shield" CTA in amber-warm

---

## Frame 7 — Share

**Background:** ink-deep (no breathing — this screen is the artifact)

**Content — `card-art` block** (full-width, 9:16 aspect, max-height 560):
- Background gradient: indigo-deep → indigo-primary → indigo-night
- 18 sparkles, sparkleAnim marker
- **Header row:** "MY HLHP WEEK" label gold-tint + "Week 25 · Jun 16–22" caption
- 28 px gap
- **Big number "72":** display-celebration style, white, with "/100" superscript
- 6 px gap
- **Trend pill:** green-leaf alpha background, trending-up icon + "+4 from last week"
- 26 px gap
- **Mini chart:** 7 vertical bars (Mon–Sun), heights 62/70/75/68/54/80/82, colour-coded by day's verdict, scaleY animation marker
- Day labels M T W T F S S below
- 22 px gap
- **Verdict line:** "Mostly steady · 1 humidity day · streak intact"
- 32 px gap
- **Footer row:** "HLHP" logo + "Baner, Pune"
- **Corner mascot:** absolute, bottom 80 px / right 22 px, scale 1 + slight rotate

**Below card-art — share row** (56 px, ink-deep background):
- 3 buttons: Story (indigo), WhatsApp (green-deep), Save (indigo-deep) — equal-width, icon + label

---

## Frame 8 — Good Day

**Background:** linear-gradient `{semantic.verdict.celebration}` → `{core.colour.amber-light}` → `{core.colour.amber-warm}` (vertical)

**Content (full overlay with confetti rain marker):**
- replay-bar (white-tinted): "Your best stretch this month"
- 8 px gap
- "CELEBRATE" label (ink-deep 0.7 alpha)
- 6 px gap
- **Headline "YOU HAD A GREAT WEEK"** — h1-celebration, white, text-shadow drop, letterPop marker (each letter)
- 8 px gap
- Sub-line "5 of your best 7 days happened this week" — body, white at 0.95 alpha
- 12 px gap
- **Mascot/celebrating** 120×140 with celebJump marker
- 14 px gap
- **Stats row** — 3 equal columns (Avg SFI 78 / hr Sleep avg 7.2 / Symptoms 2), each in a white-translucent card
- 18 px gap
- **Bottle card** (white-translucent): bottle icon + "BOTTLE THIS ROUTINE" label + 3 checked bullet items + "Save as my 'good week' recipe" CTA (ink-deep with gold text)

---

## Grid alignment

All frames should snap to an 8 px baseline grid. Major padding uses spacing tokens (16, 20, 24). Card internal padding uses 14 px to match the prototype exactly. Card-to-card gap is 10–14 px (visual rhythm) — use 12 as the default.
