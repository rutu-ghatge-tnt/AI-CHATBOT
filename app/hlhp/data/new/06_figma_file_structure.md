# HLHP Master — Figma File Structure

## Pages

```
🎨 01 · Foundations
   ├── Tokens (colour swatches, type ramp, spacing scale, radii, shadows, easing curves)
   └── Particle reference (humidity / ember / heat / idea / sparkle / confetti / burst / floatup samples)

🧱 02 · Components
   ├── HLHP/Atoms/
   │     ├── Chip (rest / hover / selected)
   │     ├── CountButton (rest / selected)
   │     ├── Tab (rest / active)
   │     ├── Badge (earned / locked)
   │     └── DayDot (done / today / pending)
   ├── HLHP/Molecules/
   │     ├── Card (default / alert / insight-blue / insight-amber / insight-purple / captured-data)
   │     ├── CoachBubble
   │     ├── Toolbar
   │     ├── BadgeStrip
   │     └── CTAButton (primary / secondary / share)
   ├── HLHP/Organisms/
   │     ├── ScoreRing (idle / dipping marker)
   │     ├── MoodOrb
   │     ├── PushBanner
   │     ├── StampCard
   │     └── ShareCardArt
   └── HLHP/Characters/
         └── Mascot (default / waving / worried / celebrating / walking)
              with accessory layer (trophy / umbrella / fan / notepad / eyeglasses) — boolean visibility per state

📱 03 · Screens
   ├── 0 · Onboarding (420×720, overlay)
   ├── 1 · Hello
   ├── 2 · Log
   ├── 3 · Streak
   ├── 4 · Surge
   ├── 5 · Recap
   ├── 6 · Patterns
   ├── 7 · Share
   └── 8 · Good Day

🎬 04 · Flows
   ├── Daily journey (Onboarding → Hello → Log → Streak)
   ├── Surge response (Hello → Surge → Log)
   ├── Weekly recap loop (Recap → Share)
   ├── Insight discovery (Hello → Patterns → set alert)
   └── Celebration moment (Streak → Good Day → Share)

📐 05 · Spec sheets
   ├── Per-screen handoff (dimensions, animations, sound triggers — from the master CSVs)
   ├── Animation timing reference (cubic-bezier visualised)
   └── Accessibility notes (touch targets, contrast ratios, screen reader)
```

## Frames per page — recommended layout

**Foundations page** — single 1440 × 1024 frame, columned layout, view as design system poster.

**Components page** — 9 component frames in a 3 × 3 grid, each frame 400 × 400 with the component centred + variant grid below.

**Screens page** — 9 phone frames (420 × 720) in a 5 × 2 grid (5 across, 2 rows), 80 px gutters. Onboarding overlay positioned next to Hello with a connector annotation.

**Flows page** — 5 flow frames, each containing the relevant screens as smart-instances + arrows + decision labels. Use FigJam-style connector arrows.

**Spec sheets page** — text-heavy frames at 1440 × 2000, one per screen, with annotated callouts.

## Naming convention (file-wide)

| Type | Pattern | Example |
|---|---|---|
| Page | emoji + number + name | `🎨 01 · Foundations` |
| Frame | screen number + name | `1 · Hello` |
| Component (master) | category/atomic-level/name | `HLHP/Molecules/CoachBubble` |
| Variant property | lowercase-kebab | `state=rest`, `tone=alert`, `mood=worried` |
| Layer | snake_case with prefix for special | `score_ring`, `[anim] flame_glow`, `[icon] ti-trophy` |

Prefix conventions:
- `[anim]` — layer drives an animation
- `[icon]` — Tabler icon reference
- `[bg]` — background-only decoration
- `[tmp]` — temporary placeholder (should be removed before handoff)

## Variables setup (Figma Variables, not Tokens Studio)

If using native Figma Variables instead of Tokens Studio:

1. Create a **Modes** collection with one mode: `default` (leave room for future `dark` mode).
2. Create variable groups:
   - `colour/core/*` — from `01_design_tokens.json` → `core.colour`
   - `colour/semantic/*` — from `01_design_tokens.json` → `semantic`
   - `spacing/*` — from `core.spacing`
   - `radius/*` — from `core.radius`
3. Bind component fills, strokes, and Auto Layout padding to variables.
4. For typography, use Figma Text Styles imported from `02_typography.json`.

## Handoff exports

For developers, export the following from the Spec page:
- Each frame as PNG @2x
- Component variant matrices as PNG
- Tokens as CSS Custom Properties (use Variables to CSS plugin)
- Mascot poses as individual SVGs

For QA, export the Flows page as a single PDF showing every user journey end-to-end.
