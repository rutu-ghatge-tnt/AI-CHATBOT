# HLHP Component Library — Figma Spec

12 reusable components. Each lives on the **Components** page in the Figma file. Use Auto Layout everywhere — none of these should have manual positioning inside the component frame.

---

## 1. `Chip` (symptom selector)

**Variants:** state = `rest` / `hover` / `selected`

- **Rest:** background `{semantic.chip.rest-bg}`, 0.5px border `{semantic.chip.rest-border}`, text `{semantic.text.primary}` at 13/1.4
- **Hover:** translate Y -2px, drop shadow `{core.shadow.card-rest}`
- **Selected:** background `{semantic.chip.selected-bg}`, border `{semantic.chip.selected-border}`, text `{semantic.chip.selected-text}` at 13/1.4 medium

**Auto Layout:** horizontal, padding 9px × 16px, gap 0, radius `{core.radius.round}`. Hug width.

---

## 2. `CountButton`

**Variants:** state = `rest` / `selected`

- **Rest:** 48×44, white surface, 0.5px line, radius `{core.radius.s}`, text 14/centered
- **Selected:** background `{semantic.chip.selected-bg}`, border `{semantic.chip.selected-border}`, text amber-rust, scale 1.05, weight semibold

---

## 3. `CTAButton`

**Variants:** style = `primary` / `secondary` / `share`

- **Primary:** ink-deep background, cream text, pulseGlow shadow at rest, padding 13×26, radius round
- **Secondary:** transparent background, 0.5px line, ink-deep text, padding 7×14, radius `{core.radius.s}`
- **Share:** indigo background, white text, gap 6 between icon + label

---

## 4. `Card` (insight / alert / capture)

**Variants:** tone = `default` / `alert` / `insight-blue` / `insight-amber` / `insight-purple`

- **Default:** white background, 0.5px line-warm border, padding 14, radius `{core.radius.m}`
- **Alert:** white background, 0.5px red-pale border, alert-glow shadow
- **Insight-blue (Patterns hero):** indigo gradient, white text
- **Captured-data card:** indigo-cool-pale background, padding 12×14, radius `{core.radius.s}`

**Auto Layout:** vertical, gap 6, padding 14.

---

## 5. `ScoreRing`

**Variants:** state = `idle` / `dipping` (animated only — design only the idle frame)

- **Outer:** 130×130, conic-gradient ring (this maps to a Figma frame with a stroke + clip-path equivalent — designers should mock with a circle + arc)
- **Inner:** 100×100 cream disk, centred
- **Digits:** score-digit text style centred + caption ("/100 today") below
- **Ring color rules:**
  - 75–100: `{semantic.verdict.balanced-best}`
  - 60–74: `{semantic.verdict.humidity}`
  - 50–59: `{semantic.verdict.warm-day}`
  - 0–49: `{semantic.verdict.critical}`

---

## 6. `MoodOrb` (Hello tab)

- 150×150 circle
- Radial gradient: gold centre → amber-light mid → amber-warm edge
- Inner highlight bubble (white at 0.4 alpha, top-left)
- orb-glow shadow
- Mascot SVG placed at bottom, half-tucked behind orb

---

## 7. `Mascot` (sheep character)

**Variants:** mood = `default` / `waving` / `worried` / `celebrating` / `walking`

Single base SVG with conditional accessory groups:
- **default:** neutral, soft smile
- **waving:** small hand ellipse rotated, accessible on Hello
- **worried:** red eyebrow lines above eyes (Surge)
- **celebrating:** raised "arms" (curved limbs), yellow star ear ornaments (Good Day)
- **walking:** smaller profile, no ears, simpler face (Recap)

**Future moods to scaffold:** trophy under arm (post-streak milestone), umbrella (humidity), tiny fan (heat), notepad (post-log), eyeglasses (post-Patterns view).

---

## 8. `CoachBubble`

- Background: linear-gradient ink-deep → indigo-deep, padding 10×14
- Avatar: 28×28 circle, gold-bright gradient, single letter (currently "C"), bold ink-deep text
- Speaker triangle: 12×12 rotated 45° in ink-deep, positioned -6px top
- Body text: caption white, with a label-small "YOUR COACH" tag in gold-bright above
- Shadow: card-elevated

**Auto Layout:** horizontal, gap 10, align-items flex-start, padding 10×14, radius `{core.radius.m}`

---

## 9. `Badge`

**Variants:** state = `earned` / `locked`

- 26×26 circle
- **Earned:** amber gradient + green check corner-mark (11×11, bottom-right, with 1.5px cream border), Tabler icon 14px in white
- **Locked:** surface-rest background, ink-soft icon at 14px

**Tooltip:** ink-deep pill, 4×8 padding, fade-in on hover, white text

---

## 10. `Tab`

**Variants:** state = `rest` / `active`

- Icon 16×16 stacked above 9–10px label
- Padding 8×4, gap 2 between icon and label, radius 8×8×0×0 (top corners only)
- **Active:** white background, ink-deep text, soft top-shadow

---

## 11. `DayDot` (streak grid)

**Variants:** state = `done` / `today` / `pending`

- 1:1 aspect ratio circle
- **Done:** amber gradient + white letter
- **Today:** indigo gradient + white letter + 4px halo shadow
- **Pending:** surface-rest + transparent letter

---

## 12. `Particle systems` (visual reference only — Figma frames as documentation)

Place each particle type as a small visual chip in the foundations page with annotations:
- Humidity droplet (6×8, indigo, 50% 50% 50% 0 radius + 45° rotation)
- Ember (6×6, amber circle)
- Heat mote (4×4, amber circle)
- Idea particle (6×8, purple-tinted droplet)
- Sparkle (6–16px, gold star SVG)
- Confetti (8×12, multi-colour rect)
- Burst dot (8×8, multi-colour pastel)
- Float-up emoji (18px text, randomised glyph)

---

## Component naming convention

`HLHP/Atoms/Chip`, `HLHP/Atoms/CountButton`, `HLHP/Molecules/Card`, `HLHP/Molecules/CoachBubble`, `HLHP/Organisms/ScoreRing`, `HLHP/Organisms/MoodOrb`, `HLHP/Characters/Mascot`.

This follows atomic design and lets designers find anything by category in 2 clicks.
