/**
 * Raw JSON shape from POST /api/hlhp/scan (FastAPI ScanResponse).
 * Mapped to UI ScanResponse in scanAdapter.ts.
 */
import type { CoachWrap, FlashAlert, ImpactLine, SeverityBand } from "./types";

export interface BackendSymptomChip {
  keyword: string;
  highlighted: boolean;
}

export interface BackendAlertTile {
  rule_id: string;
  l1: string;
  l2: string;
  coach_wrap?: CoachWrap | null;
  how_text?: string | null;
  factor?: string;
}

export interface BackendEnvSnapshot {
  user_id?: string | null;
  city: string;
  timestamp: string;
  uvi: number;
  aqi_cpcb: number;
  rh_pct: number;
  temp_c: number;
  season: string;
  uvi_band: string;
  aqi_band: string;
  rh_band: string;
  temp_band: string;
}

export interface BackendWeatherVisuals {
  weather_type?: string | null;
  skin_care_tip?: string | null;
  screen_variants: {
    screen?: string | null;
    weather_type?: string | null;
    background_image?: string | null;
    animal_image?: string | null;
  }[];
}

export interface BackendScanResponse {
  snapshot_version: string;
  workbook_version?: string | null;
  scenario_library_version?: string | null;
  mode: "guest" | "personalised";
  concern_id?: string | null;
  env_snapshot: BackendEnvSnapshot;
  outdoor_ok_score: number;
  outdoor_ok_band_text: string;
  mood_verdict_today: string;
  mood_headline?: string | null;
  strip_headline?: string | null;
  forecast_oneliner?: string | null;
  sudden_event_tags: string[];
  alert_count_label?: string | null;
  symptom_chips?: BackendSymptomChip[];
  user_first_name?: string | null;
  alerts: BackendAlertTile[];
  profile_nudge?: string | null;
  sfi?: number | null;
  personal_sfi?: number | null;
  band?: SeverityBand | null;
  action_cluster?: string | null;
  risk?: number | null;
  risk_label?: string | null;
  confidence?: string | null;
  flash_alert?: FlashAlert | null;
  impacts?: ImpactLine[];
  evidence_cell?: {
    id: string;
    factor: string;
    band: string;
    evidence: string;
    pmids: string[];
    confidence: string;
    action?: string;
  } | null;
  weather_visuals?: BackendWeatherVisuals | null;
  skin_care_tip?: string | null;
  weather_api_url?: string | null;
  raw_weather_payload?: Record<string, unknown> | null;
}
