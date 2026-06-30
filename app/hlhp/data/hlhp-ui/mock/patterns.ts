/**
 * mock/patterns.ts — CLIENT-ONLY pattern enrichment for the Patterns tab.
 *
 * The real backend (/v2/patterns) returns mined patterns ONLY as
 * { pattern, match_pct, n, driver } once >=5 logs exist. The prototype's
 * Patterns screen is richer: 3 insight cards with % ribbons (68–83),
 * mini timelines, weekday/weekend grids, hour charts, correlation bars.
 *
 * The % match values and the decorative mini-charts here are MOCK. The card
 * BODIES come from the symptom_explainer endpoint (real-shaped), and the
 * ribbon match % uses the real `match_pct` when available, falling back to
 * these decorative numbers.
 */
import type { SuddenEventTag } from "@/api/types";

export interface InsightCard {
  id: string;
  title: string;
  matchPct: number; // ribbon — MOCK unless backed by real match_pct
  ribbonColor: "insight" | "good" | "warmth";
  body: string; // filled from symptom_explainer (real-shaped)
  chart: "timeline" | "weekgrid" | "hours";
  ctaLabel: string;
  ctaTag: SuddenEventTag | "sleep" | "shield";
}

// decorative correlation fills for the timeline mini-chart (15 slots)
// 0 = base, 1 = "itchy" hit, 2 = "humid" hit
export const TIMELINE_PATTERN = [0, 0, 1, 0, 2, 1, 0, 1, 2, 0, 1, 0, 0, 2, 1];

// weekday/weekend grid (7 cells): true = weekend "best window"
export const WEEK_PATTERN = [false, false, false, false, false, true, true];

// hour chart heights (12 bars, %) — morning dust spike at index 1–2
export const HOUR_PATTERN = [30, 85, 78, 45, 40, 38, 42, 50, 48, 44, 36, 30];
export const HOUR_SPIKE_INDEXES = [1, 2];

export const INSIGHT_CARDS: InsightCard[] = [
  {
    id: "itchy",
    title: "Itchy days cluster on high-humidity afternoons",
    matchPct: 83,
    ribbonColor: "insight",
    body: "When Pune's RH crosses 75%, your barrier reacts within 24h.",
    chart: "timeline",
    ctaLabel: "Alert on humidity surge",
    ctaTag: "humidity_surge",
  },
  {
    id: "sleep",
    title: "Best window: weekends at home",
    matchPct: 71,
    ribbonColor: "good",
    body: "Sleep averages 7.5h on weekends vs 5.8h on weekdays.",
    chart: "weekgrid",
    ctaLabel: "Set weekday sleep reminder",
    ctaTag: "sleep",
  },
  {
    id: "dust",
    title: "Morning dust hits harder than afternoon UV",
    matchPct: 68,
    ribbonColor: "warmth",
    body: "9am PM2.5 spike accounts for most of your symptom logs.",
    chart: "hours",
    ctaLabel: "Plan a morning shield",
    ctaTag: "shield",
  },
];
