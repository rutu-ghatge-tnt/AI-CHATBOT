/**
 * lib/evidence.ts — loads & queries the exported SkinBB scenario library
 * (public/hlhp-evidence.json, from SkinBB_HLHP_Scenario_Library_v3_4.xlsx).
 *
 * This is what turns the app into a real library browser: given a city → zone →
 * weather, it computes the SFI from the REAL band-points table, finds the
 * dominant driver, and looks up the matching Master cell (real L0/L1/L2 text,
 * risk, confidence, PMID anchors, action cluster). Falls back to a tiny built-in
 * sample if the JSON can't be fetched, so the app still renders.
 */

export interface Band { label: string; range: string; points: number | null; key: string }
export interface MasterCell {
  id: string; factor: string; band: string; range: string; band_key: string;
  skin: string; concern: string; risk: number | null; risk_level: string;
  confidence: string; evidence: string; pmids: string[];
  l0: string; l1: string; l2: string; action: string; zones: string[]; season: string;
}
export interface Nugget { n: number; text: string; factor: string; source: string }
export interface Weather { temperature_c: number; aqi: number; uv_index: number; humidity_pct: number }
export interface GenderState { state: string; description: string }
export interface GenderRule {
  state: string; concern: string; risk_delta: number;
  direction: string; action: string; addendum: string; anchor: string;
}
export interface TimeOverlay { morning: string; evening: string }
export interface Evidence {
  meta?: Record<string, unknown>;
  bands: Record<string, Band[]>;
  skins: string[];
  concerns: string[];
  factors: string[];
  zones: Record<string, { code: string; name: string; cities: string[] }>;
  zone_weather: Record<string, Weather>;
  city_zone: Record<string, string>;
  master: Record<string, MasterCell>;
  compounds: unknown[];
  compound_cells: Record<string, unknown>;
  nuggets: Nugget[];
  nutrition: unknown[];
  lifestyle: unknown[];
  gender_states?: GenderState[];
  gender_rules?: Record<string, GenderRule>;
  time_overlay?: Record<string, TimeOverlay>;
}

// ---- time-of-day (3-window model from the Time-of-Day Logic sheet) -------
export type TimeWindow = "morning" | "daytime" | "evening";
export function timeWindowNow(date = new Date()): TimeWindow {
  const h = date.getHours();
  if (h < 9) return "morning";
  if (h < 16) return "daytime";
  return "evening";
}
/** the overlay clause for the dominant driver's band in the current window. */
export function timeClause(
  ev: Evidence, dom: DriverState, win: TimeWindow
): string {
  if (win === "daytime") return ""; // daytime uses the cell's own action
  const ov = ev.time_overlay?.[`${slug(dom.factor)}|${dom.band.key}`];
  if (!ov) return "";
  if (win === "morning") {
    // morning anticipatory note fires only if this factor typically rises into
    // a higher band later — for UV/AQI that's the common case, so the sheet's
    // "morning add-on" already encodes it (empty when no rise expected).
    return ov.morning;
  }
  return ov.evening;
}

// ---- gender / life-stage modifier ---------------------------------------
/** the rule for a state × concern, if one exists. */
export function genderRule(ev: Evidence, state: string, concern: string): GenderRule | null {
  if (!state || state === "Female" || state === "Male") {
    // base states still have rules for a few concerns; look them up too
  }
  return ev.gender_rules?.[`${slug(state)}|${slug(concern)}`] ?? null;
}

const FALLBACK: Evidence = {
  bands: {
    Temperature: [
      { label: "Cool", range: "15-19°C", points: 12, key: "cool" },
      { label: "Optimal", range: "20-27°C", points: 25, key: "optimal" },
      { label: "Warm", range: "28-34°C", points: 12, key: "warm" },
      { label: "Hot", range: "35-42°C", points: 5, key: "hot" },
      { label: "Extreme Heat", range: ">42°C", points: 0, key: "extreme_heat" },
    ],
    AQI: [
      { label: "Good", range: "0-50", points: 25, key: "good" },
      { label: "Satisfactory", range: "51-100", points: 18, key: "satisfactory" },
      { label: "Moderate", range: "101-200", points: 10, key: "moderate" },
      { label: "Poor", range: "201-300", points: 5, key: "poor" },
      { label: "Very Poor", range: "301-400", points: 2, key: "very_poor" },
      { label: "Severe", range: ">400", points: 0, key: "severe" },
    ],
    UV: [
      { label: "Low", range: "0-2", points: 25, key: "low" },
      { label: "Moderate", range: "3-5", points: 18, key: "moderate" },
      { label: "High", range: "6-7", points: 12, key: "high" },
      { label: "Very High", range: "8-10", points: 2, key: "very_high" },
      { label: "Extreme", range: "11+", points: 0, key: "extreme" },
    ],
    Humidity: [
      { label: "Low", range: "20-39%", points: 12, key: "low" },
      { label: "Optimal", range: "40-60%", points: 25, key: "optimal" },
      { label: "High", range: "61-79%", points: 12, key: "high" },
      { label: "Very High", range: "80-89%", points: 5, key: "very_high" },
      { label: "Extreme", range: ">90%", points: 0, key: "extreme" },
    ],
  },
  skins: ["Combination", "Dry", "Normal", "Oily", "Sensitive"],
  concerns: ["Acne", "Dryness", "Melasma", "Oily Skin", "Dark Marks (Post-Acne / PIH)"],
  factors: ["AQI", "Humidity", "Temperature", "UV"],
  zones: {
    TP: { code: "TP", name: "Temperate Plateau", cities: ["Pune", "Bengaluru", "Hyderabad"] },
    CN: { code: "CN", name: "Composite North Plains", cities: ["Delhi", "Lucknow"] },
    HH: { code: "HH", name: "Warm & Humid Coastal", cities: ["Mumbai", "Chennai"] },
    HD: { code: "HD", name: "Hot & Dry", cities: ["Jodhpur", "Jaipur"] },
  },
  zone_weather: {
    TP: { temperature_c: 28, aqi: 80, uv_index: 6, humidity_pct: 52 },
    CN: { temperature_c: 34, aqi: 210, uv_index: 8, humidity_pct: 38 },
    HH: { temperature_c: 32, aqi: 120, uv_index: 7, humidity_pct: 82 },
    HD: { temperature_c: 40, aqi: 130, uv_index: 10, humidity_pct: 18 },
  },
  city_zone: { pune: "TP", bengaluru: "TP", hyderabad: "TP", delhi: "CN", lucknow: "CN", mumbai: "HH", chennai: "HH", jodhpur: "HD", jaipur: "HD" },
  master: {},
  compounds: [],
  compound_cells: {},
  nuggets: [],
  nutrition: [],
  lifestyle: [],
};

export const slug = (s: string) =>
  String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

function valueInBand(rangeStr: string, val: number): boolean {
  const r = String(rangeStr).replace(/°C|%/g, "").replace(/[–—]/g, "-").trim();
  if (r.startsWith("<")) return val < parseFloat(r.slice(1));
  if (r.endsWith("+")) return val >= parseFloat(r.slice(0, -1));
  if (r.startsWith(">")) return val > parseFloat(r.replace(">", ""));
  if (r.includes("-")) { const [lo, hi] = r.split("-").map(parseFloat); return val >= lo && val <= hi; }
  return false;
}

export function bandFor(ev: Evidence, factor: string, val: number): Band {
  const bl = ev.bands[factor] || [];
  for (const b of bl) if (valueInBand(b.range, val)) return b;
  return bl[bl.length - 1] || { label: "?", range: "", points: 0, key: "unknown" };
}

export const DRIVER_DEFS = [
  { factor: "Temperature", key: "temp" as const, name: "Heat", col: "var(--drv-temp)" },
  { factor: "UV", key: "uv" as const, name: "UV", col: "var(--drv-uv)" },
  { factor: "Humidity", key: "humidity" as const, name: "Humidity", col: "var(--drv-humidity)" },
  { factor: "AQI", key: "aqi" as const, name: "Air (AQI)", col: "var(--drv-aqi)" },
];

export interface DriverState {
  factor: string; key: string; name: string; col: string; value: number; band: Band;
}
export function driverState(ev: Evidence, w: Weather): DriverState[] {
  const vals: Record<string, number> = {
    Temperature: w.temperature_c, UV: w.uv_index, Humidity: w.humidity_pct, AQI: w.aqi,
  };
  return DRIVER_DEFS.map((d) => ({
    ...d, value: vals[d.factor], band: bandFor(ev, d.factor, vals[d.factor]),
  }));
}
export function computeSFI(ev: Evidence, w: Weather): number {
  return driverState(ev, w).reduce((s, d) => s + (d.band.points || 0), 0);
}
export function dominantDriver(ev: Evidence, w: Weather): DriverState {
  return driverState(ev, w).slice().sort((a, b) => (a.band.points || 0) - (b.band.points || 0))[0];
}
export function pointsToLevel(p: number): "Low" | "Medium" | "High" {
  return p >= 20 ? "Low" : p >= 10 ? "Medium" : "High";
}

/** weather for a city (zone lookup), with optional surge spike. */
export function weatherForCity(ev: Evidence, city: string, surge: boolean): Weather {
  const zone = ev.city_zone[city.toLowerCase()] || "TP";
  const base = ev.zone_weather[zone] || { temperature_c: 28, aqi: 80, uv_index: 6, humidity_pct: 52 };
  if (!surge) return { ...base };
  return {
    temperature_c: Math.max(base.temperature_c, 38),
    aqi: Math.max(base.aqi, 380),
    uv_index: Math.max(base.uv_index, 11),
    humidity_pct: base.humidity_pct,
  };
}

/** the REAL Master cell for the dominant driver × profile.
 *
 * Some concerns are intentionally covered by only a subset of factors (e.g.
 * Vitiligo = UV only, Keloid/Dark Marks = UV+AQI). So we don't blindly take the
 * single lowest-points driver — we walk the drivers worst-first and return the
 * first one that actually has a cell for THIS concern + skin. That keeps a
 * Vitiligo user on a humid day looking at a real Vitiligo (UV) cell rather than
 * an Acne stand-in. Only if no factor covers the concern do we fall back. */
export function lookupCell(ev: Evidence, w: Weather, skin: string, concern: string): MasterCell | null {
  const worstFirst = driverState(ev, w).slice().sort((a, b) => (a.band.points || 0) - (b.band.points || 0));
  // 1) worst driver that has a cell for this concern + skin
  for (const d of worstFirst) {
    const hit = ev.master[`${slug(d.factor)}|${d.band.key}|${slug(skin)}|${slug(concern)}`];
    if (hit) return hit;
  }
  // 2) same, but allow Normal skin for this concern
  for (const d of worstFirst) {
    const hit = ev.master[`${slug(d.factor)}|${d.band.key}|normal|${slug(concern)}`];
    if (hit) return hit;
  }
  // 3) last resort: the dominant driver's Acne cell (concern not weather-covered)
  const dom = worstFirst[0];
  return ev.master[`${slug(dom.factor)}|${dom.band.key}|${slug(skin)}|acne`] || null;
}

/** which driver the returned cell actually came from (for the UI's "dominant" dot). */
export function lookupDriver(ev: Evidence, w: Weather, skin: string, concern: string): DriverState {
  const worstFirst = driverState(ev, w).slice().sort((a, b) => (a.band.points || 0) - (b.band.points || 0));
  for (const d of worstFirst) {
    if (ev.master[`${slug(d.factor)}|${d.band.key}|${slug(skin)}|${slug(concern)}`]) return d;
  }
  return worstFirst[0];
}

/** cities available across all zones (sorted). */
export function allCities(ev: Evidence): string[] {
  const out: string[] = [];
  Object.values(ev.zones || {}).forEach((z) => (z.cities || []).forEach((c) => { if (c && !out.includes(c)) out.push(c); }));
  return out.sort();
}

// ---- loader (client-side fetch from /public) -----------------------------
let cache: Evidence | null = null;
export async function loadEvidence(): Promise<Evidence> {
  if (cache) return cache;
  try {
    const res = await fetch("/hlhp-evidence.json");
    if (!res.ok) throw new Error("not ok");
    cache = (await res.json()) as Evidence;
  } catch {
    cache = FALLBACK;
  }
  return cache;
}
export function evidenceFallback(): Evidence {
  return FALLBACK;
}
