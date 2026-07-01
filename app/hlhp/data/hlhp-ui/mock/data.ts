/**
 * mock/data.ts — CLIENT-ONLY mock dataset for the HLHP UI.
 *
 * Everything in this file is fabricated on the client. No network calls.
 * Shapes match api/types.ts (which in turn mirror the real backend), so the
 * UI is identical whether it reads this or a live `/v2/*` engagement service.
 *
 * Brand voice: SFI capitalized; proper-noun band names; plain language; no
 * product recommendations; "information" not "advice".
 *
 * The data is internally consistent:
 *   • a 30-day SFI trend with ONE engineered surge (~14 days ago)
 *   • daily logs that reference real symptoms + dates
 *   • feelings/most-fired-mood derived from those logs
 * so Recap, Share, Patterns and Good Day all agree with each other.
 */
import type {
  SeverityBand,
  MascotMood,
  SuddenEventTag,
  DailyLog,
} from "@/api/types";
import { localDateKey } from "@/lib/dates";

// ---- profile (would come from onboarding) --------------------------------
export const MOCK_USER = {
  user_id: "demo-user",
  name: "Ajit",
  city: "Baner",
  zone: "TP", // Pune belt
  latitude: 18.56,
  longitude: 73.78,
  skin_type: "Combination",
  concern: "Acne",
};

// v2 Log chips — Dry / Oily / Dull / Breakout / Spots (multi-select).
// "Spots" added because acne often leaves marks behind. Breakout & Spots
// reveal a face-area picker (incl. "Full face"); the others don't.
const SYMPTOM_CHIPS = ["dry", "oily", "dull", "breakout", "spots"];

// ---- band ramp by SFI ----------------------------------------------------
export function bandForSfi(sfi: number): SeverityBand {
  if (sfi >= 85) return "Paradise Mode";
  if (sfi >= 70) return "Smooth Sailing";
  if (sfi >= 55) return "Guard Up";
  if (sfi >= 40) return "Battle Stations";
  if (sfi >= 25) return "Hostile Mode";
  return "Code Red";
}
const MOOD: Record<SeverityBand, MascotMood> = {
  "Paradise Mode": "radiant",
  "Smooth Sailing": "happy",
  "Guard Up": "watchful",
  "Battle Stations": "concerned",
  "Hostile Mode": "stressed",
  "Code Red": "alarmed",
};
export const moodForBand = (b: SeverityBand): MascotMood => MOOD[b] ?? "neutral";

// ---- deterministic pseudo-random so the demo looks the same each load ----
function seeded(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - n);
  return localDateKey(d);
}

/**
 * Build a 30-day SFI series ending today.
 * Baseline ~66–74, with a dip to ~52 around 14 days ago (the "surge"),
 * recovering after. Returns newest-last.
 */
// driver tag per day so Recap can colour each mark (humidity/uv/temp/aqi/comfort)
export type DayDriver = "comfort" | "humidity" | "uv" | "temp" | "aqi";
export function buildTrend(days = 30): { date: string; sfi: number | null; driver: DayDriver }[] {
  const rand = seeded(4242);
  const out: { date: string; sfi: number | null; driver: DayDriver }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    let sfi = 69 + Math.round((rand() - 0.5) * 8); // 65–73 wobble
    let driver: DayDriver = "comfort";
    if (i <= 15 && i >= 13) { sfi = 52 + Math.round((rand() - 0.5) * 4); driver = "temp"; }        // heat wave ~14d ago
    else if (i <= 8 && i >= 6) { sfi = 58 + Math.round((rand() - 0.5) * 4); driver = "humidity"; } // humidity wave ~7d ago
    else if (i === 5) { sfi = 60; driver = "aqi"; }                                                // dust spike
    else if (sfi < 64) driver = (["humidity", "uv"] as DayDriver[])[Math.floor(rand() * 2)];
    const logged = !(i === days - 2 || i === days - 12);
    out.push({ date: isoDaysAgo(i), sfi: logged ? Math.max(20, Math.min(92, sfi)) : null, driver });
  }
  return out;
}

export const MOCK_TREND_30 = buildTrend(30);

// ---- daily logs (symptom events) — v2 vocabulary (Dry/Oily/Dull/Breakout/Spots)
const LOGGED_SYMPTOMS = ["dry", "breakout", "dull", "oily", "spots", "breakout", "dull", "oily"];
export function buildDailyLogs(): DailyLog[] {
  const rand = seeded(99);
  const trendByDate = new Map(MOCK_TREND_30.map((t) => [t.date, t.sfi]));
  // place ~8 logs across the last 23 days
  const offsets = [0, 2, 4, 8, 11, 14, 19, 23];
  return offsets.map((off, idx) => {
    const date = isoDaysAgo(off);
    return {
      date,
      symptom: LOGGED_SYMPTOMS[idx % LOGGED_SYMPTOMS.length],
      sfi: trendByDate.get(date) ?? 60 + Math.round(rand() * 10),
    };
  });
}
export const MOCK_DAILY_LOGS = buildDailyLogs();

// feelings tally + most fired
export function feelingsTally(logs: DailyLog[]) {
  const f: Record<string, number> = {};
  for (const l of logs) if (l.symptom) f[l.symptom] = (f[l.symptom] ?? 0) + 1;
  const mostFired =
    Object.entries(f).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  return { feelings: f, mostFired };
}

// ---- sudden events (drives Surge tab + Recap callouts) -------------------
export const MOCK_SUDDEN_EVENTS: {
  date: string;
  tag: SuddenEventTag;
  from: number;
  to: number;
}[] = [
  { date: isoDaysAgo(14), tag: "heat_surge", from: 78, to: 54 },
  { date: isoDaysAgo(7), tag: "humidity_surge", from: 71, to: 58 },
];

// today's live-ish weather for the configured zone (mirrors engine ZONE_WEATHER TP)
export const MOCK_WEATHER = {
  temperature_c: 28,
  humidity_pct: 52,
  uv_index: 6,
  aqi: 80,
  summary: "summer-warm",
};

// when force_surge is on, the engine bumps aqi/uv — mirror that here
export const MOCK_WEATHER_SURGE = {
  temperature_c: 33,
  humidity_pct: 58,
  uv_index: 11,
  aqi: 380,
  summary: "heat spike",
};

export { SYMPTOM_CHIPS };

// ---- hourly SFI timeline (Surge spike chart) ----------------------------
export function buildTimeline(surge: boolean) {
  // 9am → 6pm, dipping mid-afternoon on a surge day
  const hours = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
  const calm = [76, 75, 74, 72, 70, 71, 73, 74, 76, 78];
  const spike = [76, 70, 60, 54, 50, 52, 58, 62, 68, 72];
  const vals = surge ? spike : calm;
  return hours.map((h, i) => ({
    slot_hour: h,
    sfi: vals[i],
    label: h <= 12 ? `${h}am` : `${h - 12}pm`,
  }));
}

// ---- symptom explainer copy (Patterns card bodies) ----------------------
// Plain-language, information-not-advice, India-context. No product names.
export const EXPLAINERS: Record<
  string,
  { title: string; sections: { heading: string; body: string }[] }
> = {
  itchy: {
    title: "Itchiness & your skin barrier",
    sections: [
      {
        heading: "What's happening",
        body: "Itch usually reads as a barrier under stress. When humidity climbs past ~75% RH, sweat sits on the skin longer and the surface swells slightly — nerve endings get more reactive within a day.",
      },
      {
        heading: "Your pattern",
        body: "Your itchy days cluster on high-humidity Pune afternoons. The barrier tends to react within 24h of a humidity jump.",
      },
    ],
  },
  breakout: {
    title: "Breakouts & sweat-clogged pores",
    sections: [
      {
        heading: "What's happening",
        body: "Heat and sweat mix with surface oil and can block pores. In warm, sticky weather this shows up a day or two after the spike, not the same hour.",
      },
      {
        heading: "Your pattern",
        body: "Most of your breakout logs follow warm, high-AQI mornings. Dust appears to matter more than midday UV for you.",
      },
    ],
  },
  dry: {
    title: "Dryness & moisture loss",
    sections: [
      {
        heading: "What's happening",
        body: "Dry air and indoor cooling pull water out of the top layer. The skin can feel tight before it looks flaky.",
      },
      {
        heading: "Your pattern",
        body: "Your dryness logs rise on lower-humidity days and after long AC stretches.",
      },
    ],
  },
  red: {
    title: "Redness & heat reactivity",
    sections: [
      {
        heading: "What's happening",
        body: "Surface blood vessels widen in heat, so the skin can flush. Pollution can add to the reactive feeling.",
      },
      {
        heading: "Your pattern",
        body: "Redness shows on your hottest feels-like days, easing as evening cools.",
      },
    ],
  },
  oily: {
    title: "Oiliness & warm weather",
    sections: [
      {
        heading: "What's happening",
        body: "Oil glands run faster as temperature rises, so midday shine is common in summer.",
      },
      {
        heading: "Your pattern",
        body: "Your oily logs track the warmest part of the day and settle by night.",
      },
    ],
  },
  tight: {
    title: "Tightness after cleansing",
    sections: [
      {
        heading: "What's happening",
        body: "A tight feeling often means the surface lost a little too much water or oil. Low humidity makes it more noticeable.",
      },
      {
        heading: "Your pattern",
        body: "Tightness appears on your driest, low-humidity days.",
      },
    ],
  },
  dull: {
    title: "Dullness & buildup",
    sections: [
      {
        heading: "What's happening",
        body: "Dust and dead-cell buildup can scatter light, so skin looks flat. High-AQI stretches make this more likely.",
      },
      {
        heading: "Your pattern",
        body: "Your dull logs line up with the haziest, higher-AQI days.",
      },
    ],
  },
};
