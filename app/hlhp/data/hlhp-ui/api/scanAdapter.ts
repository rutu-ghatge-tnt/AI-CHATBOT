/**
 * Maps POST /api/hlhp/scan (FastAPI) → UI ScanResponse.
 * Weather API fields pass through unchanged (visuals, payload, skin_care_tip).
 */
import type {
  ActionCluster,
  ScanResponse,
  SuddenEventTag,
  SeverityBand,
} from "./types";
import type { BackendScanResponse } from "./backendScanTypes";
import { MOCK_USER, moodForBand, bandForSfi, SYMPTOM_CHIPS } from "@/mock/data";

const SURGE_TAGS = new Set<SuddenEventTag>([
  "heat_surge",
  "humidity_surge",
  "pollution_surge",
  "uv_surge",
]);

const ACTION_CLUSTERS = new Set<ActionCluster>([
  "Maintain",
  "Shield",
  "Balance",
  "Hydrate",
  "Calm",
  "Brighten",
]);

function asActionCluster(value: string | null | undefined): ActionCluster {
  const v = (value ?? "Maintain").trim() as ActionCluster;
  return ACTION_CLUSTERS.has(v) ? v : "Maintain";
}

function asSuddenTags(tags: string[]): SuddenEventTag[] {
  return tags.filter((t): t is SuddenEventTag => SURGE_TAGS.has(t as SuddenEventTag));
}

function weatherSummary(env: BackendScanResponse["env_snapshot"], impacts: ScanResponse["impacts"]): string {
  if (impacts.length) {
    const top = [...impacts].sort((a, b) => {
      const rank = { High: 0, Medium: 1, Low: 2 };
      return rank[a.level] - rank[b.level];
    })[0];
    return `${top.name.toLowerCase()}-led`;
  }
  return env.season ? `${env.season.replace(/_/g, "-")}` : "today";
}

export function mapBackendScanToUi(
  raw: BackendScanResponse,
  ctx: {
    userId?: string;
    localTime?: string;
    city?: string;
    zone?: string | null;
  } = {}
): ScanResponse {
  const env = raw.env_snapshot;
  const sfi = raw.sfi ?? raw.outdoor_ok_score ?? 0;
  const band = (raw.band ?? bandForSfi(sfi)) as SeverityBand;
  const flash = raw.flash_alert ?? {
    level: "L0" as const,
    mode: band,
    l0: raw.strip_headline ?? raw.mood_headline ?? band,
    l1: raw.forecast_oneliner ?? raw.alerts[0]?.l2 ?? "",
    tip: raw.alerts[0]?.how_text ?? "",
  };
  const impacts = raw.impacts ?? [];
  const topAlert = raw.alerts[0];
  const name =
    raw.user_first_name?.trim() ||
    (ctx.userId && ctx.userId !== "demo-user" ? undefined : MOCK_USER.name) ||
    "Friend";
  const coach = topAlert?.coach_wrap ?? {};

  return {
    user_id: ctx.userId ?? env.user_id ?? MOCK_USER.user_id,
    name,
    date: (ctx.localTime ?? env.timestamp).slice(0, 10),
    city: env.city || ctx.city || MOCK_USER.city,
    zone: ctx.zone ?? null,
    sfi,
    personal_sfi: raw.personal_sfi ?? null,
    band,
    mood_verdict_today: moodForBand(band),
    risk: raw.risk ?? 1,
    risk_label: raw.risk_label ?? "Low",
    confidence: raw.confidence ?? "Calibrated",
    weather: {
      temperature_c: env.temp_c,
      humidity_pct: env.rh_pct,
      uv_index: env.uvi,
      aqi: env.aqi_cpcb,
      summary: weatherSummary(env, impacts),
    },
    action_cluster: asActionCluster(raw.action_cluster),
    alerts: [
      {
        level: flash.level,
        text: topAlert?.l2 ?? flash.l1,
        coach_wrap: {
          greeting: coach.greeting ?? (name ? `Good morning, ${name}` : undefined),
          forward_hook: coach.forward_hook ?? raw.strip_headline ?? flash.l0,
          effort_recognition: coach.effort_recognition,
          l2: coach.l2 ?? raw.forecast_oneliner ?? flash.l1,
        },
      },
    ],
    flash_alert: flash,
    impacts,
    sudden_event_tags: asSuddenTags(raw.sudden_event_tags ?? []),
    symptom_chips:
      raw.symptom_chips?.map((c) => c.keyword) ??
      SYMPTOM_CHIPS,
    evidence_cell: raw.evidence_cell
      ? {
          id: raw.evidence_cell.id,
          factor: raw.evidence_cell.factor,
          band: raw.evidence_cell.band,
          evidence: raw.evidence_cell.evidence,
          pmids: raw.evidence_cell.pmids ?? [],
          confidence: raw.evidence_cell.confidence,
        }
      : undefined,
    profile_nudge: raw.profile_nudge ?? null,
    weather_visuals: raw.weather_visuals ?? null,
    skin_care_tip: raw.skin_care_tip ?? raw.weather_visuals?.skin_care_tip ?? null,
    weather_api_url: raw.weather_api_url ?? null,
    raw_weather_payload: raw.raw_weather_payload ?? null,
  };
}
