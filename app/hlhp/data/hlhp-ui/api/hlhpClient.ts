/**
 * api/hlhpClient.ts — the ONE place the UI talks to "the backend".
 *
 * Per the build decision, this exposes the task-spec `/api/hlhp/*` surface and
 * MOCKS every call client-side (no network). It is structured so flipping
 * `USE_MOCK` to false swaps to live `fetch` with zero changes elsewhere.
 *
 * ────────────────────────────────────────────────────────────────────────
 *  IMPORTANT — what the REAL backend actually exposes (this repo):
 *  FastAPI routes are mounted at `/api/hlhp/*` (see app/hlhp/api/). When you wire
 *  live data, point each method below at its real route (mapping in comments):
 *
 *    scan(...)               → POST /api/hlhp/scan
 *    symptomFeeling(...)     → POST /api/hlhp/symptom_feeling
 *    actionTap(...)          → POST /api/hlhp/action_tap
 *    history(...)            → GET  /api/hlhp/history
 *    streak(...)             → GET  /api/hlhp/streak
 *    userLog(...)            → POST /api/hlhp/log
 *    sfiTimeline(...)        → GET  /api/hlhp/sfi_timeline
 *    catchup(...)            → GET  /api/hlhp/catchup
 *    symptomExplainer(kw)    → GET  /api/hlhp/symptom_explainer/{kw}
 *    consent(...)            → GET/POST /api/hlhp/consent
 *    health()               → GET  /api/hlhp/health
 *
 *  The engine itself (hlhp_engine.py) is stateless: POST /v1/alert, GET /v1/health.
 * ────────────────────────────────────────────────────────────────────────
 */
import type {
  ScanRequest, ScanResponse,
  SymptomFeelingRequest, SymptomFeelingResponse,
  ActionTapRequest, ActionTapResponse,
  HistoryResponse,
  SfiTimelineResponse,
  CatchupResponse,
  SymptomExplainerResponse,
  ConsentResponse,
  HealthResponse,
  StreakResponse,
  UserLogRequest,
  UserLogResponse,
} from "./types";
import {
  MOCK_USER, MOCK_TREND_30, MOCK_DAILY_LOGS, MOCK_SUDDEN_EVENTS,
  MOCK_WEATHER, MOCK_WEATHER_SURGE, SYMPTOM_CHIPS,
  bandForSfi, moodForBand, feelingsTally, buildTimeline, EXPLAINERS,
} from "@/mock/data";
import {
  flashAlertFor, buildImpacts, LEARN_EXPLAINERS, LEARN_ARTICLES,
} from "@/mock/content";
import type { LearnFeed, FlashAlert, ImpactLine, SeverityBand } from "@/api/types";
import {
  type Evidence, computeSFI, dominantDriver, driverState, lookupCell,
  weatherForCity, pointsToLevel,
} from "@/lib/evidence";
import type { BackendScanResponse } from "@/api/backendScanTypes";
import { mapBackendScanToUi } from "@/api/scanAdapter";
import { localDateKey } from "@/lib/dates";

// ---- config --------------------------------------------------------------
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Master switch. Mock by default; set NEXT_PUBLIC_USE_MOCK="false" to go live. */
export const USE_MOCK =
  (process.env.NEXT_PUBLIC_USE_MOCK ?? "true").toLowerCase() !== "false";

export const ENV = {
  userId: process.env.NEXT_PUBLIC_USER_ID ?? MOCK_USER.user_id,
  city: process.env.NEXT_PUBLIC_CITY ?? MOCK_USER.city,
  lat: Number(process.env.NEXT_PUBLIC_LAT ?? MOCK_USER.latitude),
  lng: Number(process.env.NEXT_PUBLIC_LNG ?? MOCK_USER.longitude),
};

// simulate a little latency so the loading/animation states are visible
const LATENCY = USE_MOCK ? 220 : 0;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Extra log days recorded in mock mode (survives until page reload). */
const mockLoggedDates = new Set<string>();

export function mockMarkLogDay(iso?: string) {
  mockLoggedDates.add(iso ?? localDateKey());
}

function mockLoggedDateSet(): Set<string> {
  const dates = new Set(MOCK_DAILY_LOGS.map((l) => l.date));
  mockLoggedDates.forEach((d) => dates.add(d));
  return dates;
}

function mockCalendarStreak(dates: Set<string>, today: string): number {
  let n = 0;
  const d = new Date(`${today}T12:00:00`);
  while (dates.has(localDateKey(d))) {
    n += 1;
    d.setDate(d.getDate() - 1);
  }
  return n;
}

function mockLongestStreak(dates: Set<string>): number {
  if (!dates.size) return 0;
  const sorted = [...dates].sort();
  let longest = 1;
  let current = 1;
  for (let i = 1; i < sorted.length; i++) {
    const prev = new Date(`${sorted[i - 1]}T12:00:00`);
    const cur = new Date(`${sorted[i]}T12:00:00`);
    prev.setDate(prev.getDate() + 1);
    if (localDateKey(prev) === localDateKey(cur)) {
      current += 1;
      longest = Math.max(longest, current);
    } else {
      current = 1;
    }
  }
  return Math.max(longest, current);
}

function buildMockStreak(): StreakResponse {
  const dates = mockLoggedDateSet();
  const today = localDateKey();
  const current = mockCalendarStreak(dates, today);
  const longest = Math.max(mockLongestStreak(dates), current);
  const week_grid = Array.from({ length: 7 }).map((_, i) => {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() - (6 - i));
    const iso = localDateKey(d);
    return { date: iso, done: dates.has(iso), today: iso === today };
  });
  let nxt = 0;
  if (current < 7) nxt = 7 - current;
  else if (current < 30) nxt = 30 - current;
  return {
    current_streak: current,
    longest_streak: longest,
    badges: {
      first_log: dates.size >= 1,
      streak_7: current >= 7,
      streak_30: current >= 30,
    },
    days_to_next_badge: Math.max(nxt, 0),
    week_grid,
  };
}

async function live<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`HLHP API ${path} → ${res.status}`);
  return (await res.json()) as T;
}

// =========================================================================
//  CLIENT METHODS  (mock branch + live branch per call)
// =========================================================================

/** POST /scan → Hello screen (name, mood, SFI, city, weather, coach copy).
 *
 * When `opts.evidence` is supplied (the exported scenario library), the SFI,
 * mode, flash alert (real L0/L1/L2 + risk + confidence + PMID) and impact lines
 * are all computed from the REAL library for the given city × skin × concern.
 * Otherwise it returns the hand-written mock (offline fallback). */
export async function scan(
  body: ScanRequest,
  opts: { forceSurge?: boolean; evidence?: Evidence; skin?: string; concern?: string } = {}
): Promise<ScanResponse> {
  if (!USE_MOCK) {
    const city = body.city ?? ENV.city;
    const raw = await live<BackendScanResponse>(`/api/hlhp/scan`, {
      method: "POST",
      body: JSON.stringify({
        user_id: body.user_id ?? ENV.userId,
        city,
        local_time: body.local_time ?? new Date().toISOString(),
        latitude: body.latitude ?? ENV.lat,
        longitude: body.longitude ?? ENV.lng,
        force_surge: body.force_surge ?? !!opts.forceSurge,
      }),
    });
    const zone =
      opts.evidence?.city_zone?.[city.toLowerCase()] ??
      opts.evidence?.city_zone?.[ENV.city.toLowerCase()] ??
      null;
    return mapBackendScanToUi(raw, {
      userId: body.user_id ?? ENV.userId,
      localTime: body.local_time,
      city,
      zone,
    });
  }

  await wait(LATENCY);
  const surge = !!opts.forceSurge;

  // ---- real-library path -------------------------------------------------
  if (opts.evidence) {
    return scanFromEvidence(opts.evidence, body, surge, opts.skin ?? "Combination", opts.concern ?? "Acne");
  }

  const todaySfi = surge ? 32 : 78; // surge pushes into Hostile Mode
  const band = bandForSfi(todaySfi);
  const weather = surge ? MOCK_WEATHER_SURGE : MOCK_WEATHER;
  const tags = surge ? (["heat_surge"] as const) : ([] as const);
  return {
    user_id: body.user_id ?? MOCK_USER.user_id,
    name: MOCK_USER.name,
    date: body.local_time?.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
    city: body.city ?? MOCK_USER.city,
    zone: MOCK_USER.zone,
    sfi: todaySfi,
    personal_sfi: surge ? 51 : 74,
    band,
    mood_verdict_today: moodForBand(band),
    risk: surge ? 3 : 1,
    risk_label: surge ? "High" : "Low",
    confidence: "Calibrated",
    weather,
    action_cluster: surge ? "Shield" : "Maintain",
    alerts: [
      {
        level: "L1",
        text: surge
          ? "Your skin will feel this. Stay shaded between 11 and 4."
          : "Your skin reads warm. A light routine sits best today — heavy products feel sticky in this humidity.",
        coach_wrap: {
          greeting: `Good morning, ${MOCK_USER.name}`,
          forward_hook: surge
            ? "A heat surge just landed in your area — here's what it means."
            : "Your skin's reading warm and steady. Here's today in one line.",
          effort_recognition: "Day 23 of showing up — your skin notices the consistency.",
          l2: surge
            ? "Feels-like hit 41°C and UV peaked near 11. Shade and water do most of the work today."
            : "Humidity sits mid-range. Nothing dramatic — just keep it light.",
        },
      },
    ],
    flash_alert: flashAlertFor(todaySfi, surge),
    impacts: buildImpacts(weather),
    sudden_event_tags: [...tags],
    symptom_chips: SYMPTOM_CHIPS,
  };
}

/** Build a ScanResponse from the REAL scenario library for a city × profile. */
function scanFromEvidence(
  ev: Evidence, body: ScanRequest, surge: boolean, skin: string, concern: string
): ScanResponse {
  const w = weatherForCity(ev, body.city, surge);
  const sfi = computeSFI(ev, w);
  const band = bandForSfi(sfi);
  const dom = dominantDriver(ev, w);
  const cell = lookupCell(ev, w, skin, concern);

  // flash alert from the real cell (L0 / L1 / and L2 used as the surge detail)
  const flash: FlashAlert = cell
    ? {
        level: surge ? "L1" : "L0",
        mode: band,
        l0: cell.l0,
        l1: surge ? cell.l2 : cell.l1,
        tip: `Action focus: ${cell.action}${cell.zones?.length ? ` · relevant to ${cell.zones.join("/")}` : ""}.`,
      }
    : flashAlertFor(sfi, surge);

  // impact lines from real band points
  const impacts: ImpactLine[] = driverState(ev, w).map((d) => ({
    driver: d.key as ImpactLine["driver"],
    name: d.name,
    level: pointsToLevel(d.band.points || 0),
    value: d.value,
  }));

  const tagMap: Record<string, ScanResponse["sudden_event_tags"][number]> = {
    Temperature: "heat_surge", Humidity: "humidity_surge", AQI: "pollution_surge", UV: "uv_surge",
  };

  return {
    user_id: body.user_id ?? ENV.userId,
    name: MOCK_USER.name,
    date: body.local_time?.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
    city: body.city,
    zone: ev.city_zone[body.city.toLowerCase()] ?? null,
    sfi,
    personal_sfi: cell?.risk != null ? Math.max(0, sfi - cell.risk * 4) : null,
    band: band as SeverityBand,
    mood_verdict_today: moodForBand(band),
    risk: cell?.risk ?? (surge ? 3 : 1),
    risk_label: cell?.risk_level ?? (surge ? "High" : "Low"),
    confidence: cell?.confidence ?? "Calibrated",
    weather: {
      temperature_c: w.temperature_c, humidity_pct: w.humidity_pct,
      uv_index: w.uv_index, aqi: w.aqi,
      summary: `${dom.name.toLowerCase()}-led`,
    },
    action_cluster: (cell?.action as ScanResponse["action_cluster"]) ?? (surge ? "Shield" : "Maintain"),
    alerts: [
      {
        level: surge ? "L2" : "L1",
        text: cell ? (surge ? cell.l2 : cell.l1) : flash.l1,
        coach_wrap: {
          greeting: `Good morning, ${MOCK_USER.name}`,
          forward_hook: surge
            ? "A sudden surge just landed in your area — here's what your skin will feel."
            : `Your skin's reading the weather in ${body.city}. Tap the alert for the full picture.`,
          effort_recognition: "Day 23 of showing up — your skin notices the consistency.",
          l2: cell?.l2,
        },
      },
    ],
    flash_alert: flash,
    impacts,
    // surface the dominant driver as a sudden-event tag only on a real surge
    sudden_event_tags: surge ? [tagMap[dom.factor] ?? "heat_surge"] : [],
    symptom_chips: SYMPTOM_CHIPS,
    // pass through the cell's evidence + PMIDs so the UI can show traceability
    evidence_cell: cell
      ? { id: cell.id, factor: cell.factor, band: cell.band, evidence: cell.evidence, pmids: cell.pmids, confidence: cell.confidence }
      : undefined,
  };
}

/** GET /learn → Learn screen (explainers from logged symptoms + article feed). */
export async function learn(userId: string = ENV.userId): Promise<LearnFeed> {
  if (!USE_MOCK) {
    // No single live route — explainers come from /v2/symptom_explainer per
    // keyword; the article feed would come from a CMS. Kept static here.
    return live<LearnFeed>(`/v2/learn?user_id=${encodeURIComponent(userId)}`).catch(
      () => buildLearnFromMock()
    );
  }
  await wait(LATENCY);
  return buildLearnFromMock();
}
function buildLearnFromMock(): LearnFeed {
  const counts: Record<string, number> = {};
  for (const l of MOCK_DAILY_LOGS) if (l.symptom) counts[l.symptom] = (counts[l.symptom] ?? 0) + 1;
  const top = Object.keys(counts).sort((a, b) => counts[b] - counts[a]).slice(0, 3);
  const keys = top.length ? top : ["dry", "dull", "breakout"];
  return {
    explainers: keys.map((k) => LEARN_EXPLAINERS[k] ?? LEARN_EXPLAINERS.dry),
    articles: LEARN_ARTICLES,
  };
}

/** POST /symptom_feeling → Log tab chip tap. */
export async function symptomFeeling(
  body: SymptomFeelingRequest
): Promise<SymptomFeelingResponse> {
  if (!USE_MOCK) {
    return live<SymptomFeelingResponse>(`/api/hlhp/symptom_feeling`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
  await wait(LATENCY);
  if (body.selected) mockMarkLogDay(body.local_time?.slice(0, 10) || undefined);
  return {
    symptom_keyword: body.symptom_keyword,
    selected: body.selected,
    highlighted_chips: body.selected ? [body.symptom_keyword] : [],
    env_line: "Humidity surge +22pts",
    engine_learned: true,
    logs_until_pattern: 4,
  };
}

/** POST /action_tap → Streak number when a routine is completed. */
export async function actionTap(
  body: ActionTapRequest
): Promise<ActionTapResponse> {
  if (!USE_MOCK) {
    // LIVE: POST /v2/logs returns { streak }; longest tracked separately
    const r = await live<ActionTapResponse>(`/api/hlhp/action_tap`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    return r;
  }
  await wait(LATENCY);
  return { streak: 23, longest_ever: 23 };
}

/** GET /streak → Streak screen (counter + 7-day grid + badges). */
export async function streak(userId: string = ENV.userId): Promise<StreakResponse> {
  if (!USE_MOCK) {
    return live<StreakResponse>(
      `/api/hlhp/streak?user_id=${encodeURIComponent(userId)}`
    );
  }
  await wait(LATENCY);
  return buildMockStreak();
}

/** POST /log → unified symptom log (preferred live path for Log screen save). */
export async function userLog(body: UserLogRequest): Promise<UserLogResponse> {
  if (!USE_MOCK) {
    return live<UserLogResponse>(`/api/hlhp/log`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
  await wait(LATENCY);
  mockMarkLogDay(body.local_time?.slice(0, 10) || undefined);
  const s = buildMockStreak();
  return {
    logged: { date: localDateKey(), symptoms: body.symptoms },
    streak: s.current_streak,
    longest_streak: s.longest_streak,
  };
}

/** GET /history → Recap / Share / Good Day / Patterns inputs. */
export async function history(
  userId: string = ENV.userId,
  days = 15
): Promise<HistoryResponse> {
  if (!USE_MOCK) {
    // LIVE: compose GET /v2/recap?days= + /v2/streak (+ /v2/weekly-card)
    return live<HistoryResponse>(
      `/api/hlhp/history?user_id=${encodeURIComponent(userId)}&days=${days}`
    );
  }
  await wait(LATENCY);
  const trend = MOCK_TREND_30.slice(-days);
  const vals = trend.map((t) => t.sfi).filter((v): v is number => v != null);
  const avg = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
  const { feelings, mostFired } = feelingsTally(MOCK_DAILY_LOGS);
  return {
    user_id: userId,
    days,
    trend,
    daily_logs: MOCK_DAILY_LOGS,
    sfi_average: avg,
    feelings,
    most_fired_mood: mostFired,
    sudden_events: MOCK_SUDDEN_EVENTS,
    streak: 23,
    longest_streak: 23,
  };
}

/** GET /sfi_timeline → Surge hourly spike chart. */
export async function sfiTimeline(
  params: { city?: string; latitude?: number; longitude?: number; user_id?: string },
  opts: { surge?: boolean } = {}
): Promise<SfiTimelineResponse> {
  if (!USE_MOCK) {
    return live<SfiTimelineResponse>(`/api/hlhp/sfi_timeline?user_id=${encodeURIComponent(params.user_id ?? ENV.userId)}`);
  }
  await wait(LATENCY);
  const surge = !!opts.surge;
  return {
    city: params.city ?? MOCK_USER.city,
    zone: MOCK_USER.zone,
    sudden_event_tags: surge ? ["heat_surge"] : [],
    outdoor_ok_score: surge ? 54 : 78,
    points: buildTimeline(surge),
  };
}

/** GET /catchup → Recap callout / monthly narrative. */
export async function catchup(userId: string = ENV.userId): Promise<CatchupResponse> {
  if (!USE_MOCK) {
    return live<CatchupResponse>(`/api/hlhp/catchup?user_id=${encodeURIComponent(userId)}&days=30`);
  }
  await wait(LATENCY);
  return {
    user_id: userId,
    monthly_narrative:
      "30 days, one surge, streak intact. You read warm most of the month and handled the mid-month heat spike without a dropped day.",
    verdict_headline: "Stronger than May",
    verdict_sub: "Avg SFI 68 (was 61) · 0 dropped days",
    snippets: [
      "Heat surge on the 12th — SFI 78 → 54 — you handled it.",
      "Humidity wave mid-month nudged barrier-stress for a few days.",
      "Day 23 of your streak — keep it lit.",
    ],
  };
}

/** GET /symptom_explainer/{keyword} → Patterns card body copy. */
export async function symptomExplainer(
  keyword: string
): Promise<SymptomExplainerResponse> {
  if (!USE_MOCK) {
    // No live route yet → still served from static content (see header).
    return live<SymptomExplainerResponse>(`/api/hlhp/symptom_explainer/${encodeURIComponent(keyword)}`).catch(
      () => buildExplainerFromMock(keyword)
    );
  }
  await wait(LATENCY);
  return buildExplainerFromMock(keyword);
}
function buildExplainerFromMock(keyword: string): SymptomExplainerResponse {
  const e = EXPLAINERS[keyword] ?? EXPLAINERS.itchy;
  return { keyword, title: e.title, sections: e.sections };
}

/** GET/POST /consent → Onboarding. */
export async function getConsent(userId: string = ENV.userId): Promise<ConsentResponse> {
  if (!USE_MOCK) return live<ConsentResponse>(`/api/hlhp/consent?user_id=${userId}`);
  await wait(LATENCY);
  return { user_id: userId, consented: false, consented_at: null };
}
export async function postConsent(userId: string = ENV.userId): Promise<ConsentResponse> {
  if (!USE_MOCK) {
    return live<ConsentResponse>(`/api/hlhp/consent`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
  }
  await wait(LATENCY);
  return { user_id: userId, consented: true, consented_at: new Date().toISOString() };
}

/** GET /health → dev sanity check. */
export async function health(): Promise<HealthResponse> {
  if (!USE_MOCK) return live<HealthResponse>(`/api/hlhp/health`);
  await wait(60);
  return {
    status: "ok",
    library: "SkinBB_HLHP_Scenario_Library_v3_4.xlsx",
    engine_library_version: "1.0.1 (mock)",
    source: "mock",
  };
}

export const hlhpClient = {
  scan, symptomFeeling, actionTap, streak, userLog, history, sfiTimeline,
  catchup, symptomExplainer, learn, getConsent, postConsent, health,
};
export default hlhpClient;
