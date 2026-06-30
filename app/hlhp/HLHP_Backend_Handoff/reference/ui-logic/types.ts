/**
 * api/types.ts — response/request shapes for the HLHP UI.
 *
 * These mirror the *task-spec* `/api/hlhp/*` endpoint surface (scan,
 * symptom_feeling, action_tap, history, sfi_timeline, catchup,
 * symptom_explainer, consent, health).
 *
 * The field shapes are deliberately aligned with the REAL backend that ships
 * in this repo (engagement_service/engagement_api.py + hlhp_engine.py) so that
 * swapping mock → live is a thin mapping, not a rewrite. See README "real vs
 * mocked" table and api/hlhpClient.ts for the swap point.
 *
 * Brand rules honored in copy: SFI always capitalized; band names are proper
 * nouns (Paradise Mode → Smooth Sailing → Guard Up → Battle Stations →
 * Hostile Mode → Code Red); no product recommendations; "information" not
 * "advice".
 */

// ---- shared vocabulary (from hlhp_engine) --------------------------------
export type SeverityBand =
  | "Paradise Mode"
  | "Smooth Sailing"
  | "Guard Up"
  | "Battle Stations"
  | "Hostile Mode"
  | "Code Red";

export type MascotMood =
  | "radiant"
  | "happy"
  | "watchful"
  | "concerned"
  | "stressed"
  | "alarmed"
  | "neutral";

export type ActionCluster =
  | "Maintain"
  | "Shield"
  | "Balance"
  | "Hydrate"
  | "Calm"
  | "Brighten";

export type SuddenEventTag =
  | "heat_surge"
  | "humidity_surge"
  | "pollution_surge"
  | "uv_surge";

// ---- POST /scan  (Hello) -------------------------------------------------
export interface ScanRequest {
  user_id?: string;
  city: string;
  local_time: string; // ISO
  latitude?: number;
  longitude?: number;
}

export interface CoachWrap {
  greeting?: string;
  forward_hook?: string;
  effort_recognition?: string;
  l2?: string;
}

export interface ScanAlert {
  level: "L0" | "L1" | "L2";
  text: string;
  coach_wrap: CoachWrap;
}

/** Driver impact line (Temp/UV/Humidity/AQI → Low/Medium/High). */
export type ImpactDriver = "temp" | "uv" | "humidity" | "aqi";
export type ImpactLevel = "Low" | "Medium" | "High";
export interface ImpactLine {
  driver: ImpactDriver;
  name: string;
  level: ImpactLevel;
  value: number;
}

/** L0 compact + L1 detail + actionable tip (honors L0 wording convention). */
export interface FlashAlert {
  level: "L0" | "L1";
  mode: SeverityBand; // band/mode name
  l0: string; // plain hook + caring verdict, ≤20 words
  l1: string; // fuller explanation
  tip: string; // one actionable tip
}

export interface ScanResponse {
  user_id: string;
  name: string;
  date: string; // ISO date
  city: string;
  zone: string | null;
  // env SFI (0–100) — public "Skin Friendliness Index"
  sfi: number;
  personal_sfi: number | null;
  band: SeverityBand;
  mood_verdict_today: MascotMood;
  risk: number; // 0–5
  risk_label: string;
  confidence: string;
  weather: {
    temperature_c: number;
    humidity_pct: number;
    uv_index: number;
    aqi: number;
    summary: string; // e.g. "summer-warm"
  };
  action_cluster: ActionCluster;
  alerts: ScanAlert[];
  // NEW: the flash alert (L0 compact + L1 + tip) shown on Hello
  flash_alert: FlashAlert;
  // NEW: per-driver impact lines for Hello
  impacts: ImpactLine[];
  sudden_event_tags: SuddenEventTag[];
  symptom_chips: string[];
  // NEW (real-library path): traceability of the matched scenario cell
  evidence_cell?: {
    id: string; factor: string; band: string;
    evidence: string; pmids: string[]; confidence: string;
  };
}

// ---- Learn feed ----------------------------------------------------------
export interface LearnExplainer {
  keyword: string;
  title: string;
  body: string;
}
export interface LearnArticle {
  tag: string;
  driver: ImpactDriver | "basics";
  title: string;
  blurb: string;
  read_min: number;
}
export interface LearnFeed {
  explainers: LearnExplainer[];
  articles: LearnArticle[];
}

// ---- POST /symptom_feeling  (Log) ---------------------------------------
export interface SymptomFeelingRequest {
  user_id: string;
  symptom_keyword: string;
  local_time: string;
  selected: boolean;
}
export interface SymptomFeelingResponse {
  symptom_keyword: string;
  selected: boolean;
  highlighted_chips: string[];
  env_line: string; // "Humidity surge +22pts"
  engine_learned: boolean;
  logs_until_pattern: number;
}

// ---- POST /action_tap  (Streak) -----------------------------------------
export interface ActionTapRequest {
  user_id: string;
  routine_action: ActionCluster | string;
  current_time: string;
  location_city: string;
  latitude?: number;
  longitude?: number;
}
export interface ActionTapResponse {
  streak: number;
  longest_ever: number;
}

// ---- GET /history?user_id=&days=15  (Recap / Share / Good Day / Patterns)
export interface DailyLog {
  date: string;
  symptom?: string;
  sfi: number | null;
}
export interface HistoryResponse {
  user_id: string;
  days: number;
  // per-day SFI series (newest last); null = no log that day.
  // `driver` colours the day in Recap (humidity/uv/temp/aqi/comfort).
  trend: { date: string; sfi: number | null; driver?: string }[];
  daily_logs: DailyLog[];
  sfi_average: number | null;
  feelings: Record<string, number>; // symptom → count
  most_fired_mood: string | null;
  sudden_events: { date: string; tag: SuddenEventTag; from: number; to: number }[];
  streak: number;
  longest_streak: number;
}

// ---- GET /sfi_timeline  (Surge) -----------------------------------------
export interface SfiTimelineResponse {
  city: string;
  zone: string | null;
  sudden_event_tags: SuddenEventTag[];
  outdoor_ok_score: number; // 0–100 ring fill
  points: { slot_hour: number; sfi: number; label: string }[];
}

// ---- GET /catchup  (Recap callouts) -------------------------------------
export interface CatchupResponse {
  user_id: string;
  monthly_narrative: string;
  verdict_headline: string; // "Stronger than May"
  verdict_sub: string; // "Avg SFI 68 (was 61) · 0 dropped days"
  snippets: string[];
}

// ---- GET /symptom_explainer/{keyword}  (Patterns) -----------------------
export interface SymptomExplainerResponse {
  keyword: string;
  title: string;
  sections: { heading: string; body: string }[];
}

// ---- GET / POST /consent  (Onboarding) ----------------------------------
export interface ConsentResponse {
  user_id: string;
  consented: boolean;
  consented_at: string | null;
}

// ---- GET /health --------------------------------------------------------
export interface HealthResponse {
  status: string;
  library: string;
  engine_library_version: string;
  source: "mock" | "live";
}
