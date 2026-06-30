/**
 * mock/content.ts — CLIENT-ONLY content model for the v2 screens.
 *
 * L0/L1 flash alerts + tips per mode, impact-line computation, the mode ladder,
 * and the Learn feed (symptom explainers + SkinBB knowledge articles).
 *
 * All copy honors SkinBB rules: SFI capitalized; proper-noun band/mode names;
 * "information"/"guidance" never "advice"; no product/brand names; L0 = plain
 * environmental hook + caring, action-oriented verdict (≤20 words, no abstract
 * load words like "pressure"/"stress on"/"load").
 */
import type {
  SeverityBand, FlashAlert, ImpactLine, ImpactDriver, ImpactLevel,
  LearnExplainer, LearnArticle,
} from "@/api/types";

// ---- mode ladder ---------------------------------------------------------
export interface ModeDef {
  min: number;
  name: SeverityBand;
  icon: string; // tabler-ish name (UI maps to lucide)
}
export const MODES: ModeDef[] = [
  { min: 85, name: "Paradise Mode", icon: "sparkles" },
  { min: 70, name: "Smooth Sailing", icon: "smile" },
  { min: 55, name: "Guard Up", icon: "shield-half" },
  { min: 40, name: "Battle Stations", icon: "alert-triangle" },
  { min: 25, name: "Hostile Mode", icon: "flame" },
  { min: 0, name: "Code Red", icon: "siren" },
];
export function modeFor(sfi: number): ModeDef {
  return MODES.find((m) => sfi >= m.min) ?? MODES[MODES.length - 1];
}

// ---- impact thresholds (value → Low/Medium/High) -------------------------
const IMPACT_THRESHOLDS: Record<ImpactDriver, [number, number]> = {
  temp: [30, 36],
  uv: [6, 9],
  humidity: [60, 75],
  aqi: [100, 200],
};
const DRIVER_NAME: Record<ImpactDriver, string> = {
  temp: "Heat",
  uv: "UV",
  humidity: "Humidity",
  aqi: "Air (AQI)",
};
export function impactLevel(driver: ImpactDriver, value: number): ImpactLevel {
  const [lo, hi] = IMPACT_THRESHOLDS[driver];
  return value < lo ? "Low" : value < hi ? "Medium" : "High";
}
export function buildImpacts(weather: {
  temperature_c: number;
  uv_index: number;
  humidity_pct: number;
  aqi: number;
}): ImpactLine[] {
  const map: { driver: ImpactDriver; value: number }[] = [
    { driver: "temp", value: weather.temperature_c },
    { driver: "uv", value: weather.uv_index },
    { driver: "humidity", value: weather.humidity_pct },
    { driver: "aqi", value: weather.aqi },
  ];
  return map.map(({ driver, value }) => ({
    driver,
    name: DRIVER_NAME[driver],
    level: impactLevel(driver, value),
    value,
  }));
}

// ---- L0 / L1 flash alerts + tips per mode --------------------------------
const ALERT_COPY: Record<SeverityBand, { l0: string; l1: string; tip: string }> = {
  "Paradise Mode": {
    l0: "Lovely day for your skin. Enjoy it and keep your good habits going.",
    l1: "Conditions are gentle across the board. A great day to let your skin breathe and stay consistent with what's working.",
    tip: "Keep it simple and consistent — and still finish with sun protection before you head out.",
  },
  "Smooth Sailing": {
    l0: "Warm and a little sticky out there. Keep your routine light today.",
    l1: "Humidity sits mid-range and UV is moderate — nothing dramatic. Heavy creams will feel greasy and sit on the skin in this air, so a lighter layer does more for you today.",
    tip: "Go light: a gel or thin lotion now, and reapply sun protection by mid-morning.",
  },
  "Guard Up": {
    l0: "Conditions are building. Stay on top of your usual care today.",
    l1: "A couple of factors are climbing together. Your skin can handle it, but this is the day to be consistent rather than skip steps.",
    tip: "Don't skip moisturiser, and keep water handy — small, steady care beats catching up later.",
  },
  "Battle Stations": {
    l0: "Tough day for your skin. Protect it and take it easy on actives.",
    l1: "Heat and sun are pushing hard today. Strong actives can tip sensitive skin over the edge when conditions are already this demanding.",
    tip: "Pause exfoliating acids today. Shade between 11 and 4, and reapply sun protection.",
  },
  "Hostile Mode": {
    l0: "Harsh out there. Shield your skin and keep things simple today.",
    l1: "A sudden surge has dropped your SFI fast. Your barrier will feel this within hours, so today is about protection, not experimenting.",
    tip: "Cleanse, moisturise, sun-protect — nothing more. Stay shaded and hydrate through the afternoon.",
  },
  "Code Red": {
    l0: "Extreme conditions. Shield your skin now and limit time outside.",
    l1: "Multiple factors have spiked together to a rare high. Skin can react quickly today, so minimise exposure and keep your routine to the essentials.",
    tip: "Stay indoors at peak hours where you can. Bare-minimum routine, plenty of water, reapply protection often.",
  },
};
export function flashAlertFor(sfi: number, surge: boolean): FlashAlert {
  const mode = modeFor(sfi).name;
  const c = ALERT_COPY[mode];
  return { level: surge ? "L1" : "L0", mode, l0: c.l0, l1: c.l1, tip: c.tip };
}

// ---- Learn feed ----------------------------------------------------------
export const LEARN_EXPLAINERS: Record<string, LearnExplainer> = {
  dry: { keyword: "dry", title: "Tightness & moisture loss", body: "Dry air and indoor cooling pull water from the top layer, so skin feels tight before it looks flaky. It tracks your lower-humidity days." },
  oily: { keyword: "oily", title: "Midday shine in the heat", body: "Oil glands run faster as the temperature rises, so shine peaks in the warmest hours and settles by evening." },
  dull: { keyword: "dull", title: "Dullness & dust buildup", body: "Dust and dead-cell buildup scatter light, so skin looks flat. It lines up with your haziest, higher-AQI days." },
  breakout: { keyword: "breakout", title: "Breakouts & sweat-clogged pores", body: "Heat and sweat mix with surface oil and can block pores. It tends to show a day or two after a warm, high-dust spell." },
  spots: { keyword: "spots", title: "Spots left behind", body: "After a breakout calms, a mark can linger as the skin repairs. Sun exposure can make these marks look darker for longer." },
  itchy: { keyword: "itchy", title: "Itchiness & the barrier", body: "When humidity climbs past ~75%, sweat sits longer and the surface gets more reactive within a day." },
};
export const LEARN_ARTICLES: LearnArticle[] = [
  { tag: "HUMIDITY", driver: "humidity", title: "Why monsoon air makes your skin itch", blurb: "What rising humidity actually does to your barrier — and the simple routine shift that helps.", read_min: 4 },
  { tag: "AIR QUALITY", driver: "aqi", title: "Pollution & your skin: the morning-dust effect", blurb: "PM2.5 peaks early in Indian cities. Here's how a morning shield routine works.", read_min: 5 },
  { tag: "SUN", driver: "uv", title: "UV in India isn't just an afternoon problem", blurb: "Why your sun protection window is wider than you think, and how to reapply realistically.", read_min: 3 },
  { tag: "HEAT", driver: "temp", title: "Heat, sweat and breakouts — the real link", blurb: "How warm weather changes oil and pores, and what to ease off when the SFI drops.", read_min: 4 },
  { tag: "BASICS", driver: "basics", title: "What is the Skin Friendliness Index?", blurb: "A plain-language guide to your daily 0–100 SFI and the six skin-weather modes.", read_min: 2 },
];

/** Strong, ready-to-paste social caption for the Share card. */
export const SHARE_CAPTION =
  "My skin read the weather all week 🌡️\n\n" +
  "Pune hit me with a heat wave AND a humidity spike — and my barrier held. " +
  "Tracking my Skin Friendliness Index (SFI) with @skinbb so I actually know what my skin's up against each day.\n\n" +
  "This week: 69/100, up 4. 💪\n\n" +
  "#SkinBB #SkinFriendlinessIndex #ApplyKnowledgeToTheSkin #IndianSkincare #SkinHealth";

export const SHARE_HEADLINE = "My skin read the weather all week.";
export const SHARE_SUB =
  "Pune threw a heat wave and a humidity spike at me — my barrier held. " +
  "Tracking my Skin Friendliness Index with SkinBB.";
