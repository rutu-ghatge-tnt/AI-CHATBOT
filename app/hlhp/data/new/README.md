# HLHP — Figma Export Package

This folder contains everything needed to recreate the master prototype (`hlhp_fun_animated_master.html`) as a production-grade Figma file. Designed for either:

1. **Manual import** by a designer (30–60 minutes to a complete file)
2. **Programmatic push** via Figma MCP once a Figma session is connected

## File index

| File | Purpose |
|---|---|
| `01_design_tokens.json` | Tokens Studio compatible — colour, spacing, radius, shadow primitives. Import via Figma Tokens plugin. |
| `02_typography.json` | Type ramp — display, h1, h2, body, caption, label, micro. |
| `03_components_spec.md` | Component library — every reusable component with variants, states, and Auto Layout settings. |
| `04_screen_frames.md` | All 8 screens (Hello, Log, Streak, Surge, Recap, Patterns, Share, Good Day) + Onboarding overlay — frame dimensions, layout, element positions. |
| `05_user_centric_design_notes.md` | UX rationale per screen — why each design decision serves the user (not just the brand). |
| `06_figma_file_structure.md` | Page hierarchy and frame organisation for the Figma file. |

## Figma file plan (one-line summary)

A single Figma file called **HLHP — Master**, with five pages:

1. **🎨 Foundations** — colour tokens, type ramp, spacing, radii, shadows
2. **🧱 Components** — chips, buttons, cards, mascot, coach bubble, badges, score ring, etc.
3. **📱 Screens** — all 8 mobile frames at 420 × 720 px, plus onboarding overlay
4. **🎬 Flows** — connector arrows between screens showing user journey
5. **📐 Spec sheets** — handoff annotations (dimensions, animations, sound triggers)

## How to import (manual path)

1. Open the [Tokens Studio](https://docs.tokens.studio/) plugin in a fresh Figma file.
2. **Import → JSON** → upload `01_design_tokens.json` and `02_typography.json`.
3. Click **Apply** — all variables and styles are now in the file.
4. Build the 12 components from `03_components_spec.md` on the Components page.
5. Assemble the 8 screens from `04_screen_frames.md` on the Screens page.
6. Use `05_user_centric_design_notes.md` as the spec-sheet text on the Spec page.

## How to import (programmatic path — when Figma MCP is connected)

Sequence:
1. Call `mcp__figma__create_new_file` with editor type `design`, name `HLHP — Master`.
2. Call `mcp__figma__use_figma` with a script that loops the design tokens JSON and creates variables + styles.
3. Build components via `use_figma` scripts, one component at a time, with proper Auto Layout.
4. Assemble screens via `figma-generate-design` skill, section-by-section.

The `figma-use` and `figma-generate-design` skills (in this project's skill set) cover the exact API patterns.

## Design philosophy (one paragraph)

Warm cream canvas (#FBF4E8) under everything — calmer than the usual clinical-white skincare app. Indigo (#2864B8) and a deeper purple (#5240A6) carry the cognitive/insight moments. Amber (#F5B450 → #E58124) carries warmth, streaks, and celebrations. Red (#E2554F) is reserved exclusively for sudden-event alerts so the brain learns to treat it as urgent — never wasted on minor warnings. Every card lands with the same spring curve (`cubic-bezier(.34, 1.56, .64, 1)`) so the system feels coherent. A single mascot character (a soft white sheep with dark eyes) appears across screens with mood-coded accessories (umbrella in humidity, fan in heat, worried-brow lines in surge, party stars in celebration) — this is the visual continuity that turns 8 screens into one product.
