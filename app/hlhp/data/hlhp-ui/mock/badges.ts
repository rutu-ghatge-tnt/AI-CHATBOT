/**
 * mock/badges.ts — CLIENT-ONLY badge enrichment.
 *
 * The real backend (/v2/streak) only returns three booleans
 * (first_log, streak_7, streak_30). The prototype's badge strip shows 7
 * badges (4 earned + 3 locked) with tooltips. Everything beyond the three
 * real flags is decorative gamification computed here, clearly marked MOCK.
 *
 * unlock rules (client-side):
 *   first_log     → at least one symptom_feeling logged
 *   streak_7      → current streak >= 7
 *   heat_surge    → a sudden_event exists in history          (MOCK enrich)
 *   first_pattern → at least 5 logs                            (MOCK enrich)
 *   streak_30     → current streak >= 30
 *   monsoon       → locked placeholder                         (MOCK)
 *   diwali        → locked placeholder                         (MOCK)
 */
import type { LucideIcon } from "lucide-react";
import { Flag, Flame, SunMedium, Lightbulb, Trophy, CloudRain, Sparkle } from "lucide-react";

export interface BadgeDef {
  id: string;
  label: string;
  icon: LucideIcon;
  earned: boolean;
  tip: string;
  real: boolean; // true = backed by a real backend flag; false = MOCK enrichment
}

export interface BadgeInputs {
  logCount: number;
  streak: number;
  hadSuddenEvent: boolean;
}

export function computeBadges({ logCount, streak, hadSuddenEvent }: BadgeInputs): BadgeDef[] {
  const firstLog = logCount >= 1;
  const streak7 = streak >= 7;
  const streak30 = streak >= 30;
  const firstPattern = logCount >= 5;

  return [
    { id: "first_log", label: "First log", icon: Flag, earned: firstLog, real: true, tip: firstLog ? "First log" : "Log a feeling to earn" },
    { id: "streak_7", label: "7-day streak", icon: Flame, earned: streak7, real: true, tip: streak7 ? "7-day streak" : `7-day streak · ${Math.max(0, 7 - streak)} to go` },
    { id: "heat_surge", label: "Survived heat surge", icon: SunMedium, earned: hadSuddenEvent, real: false, tip: hadSuddenEvent ? "Survived a heat surge" : "Weather a surge to earn" },
    { id: "first_pattern", label: "First pattern", icon: Lightbulb, earned: firstPattern, real: false, tip: firstPattern ? "First pattern unlocked" : `First pattern · ${Math.max(0, 5 - logCount)} logs to go` },
    { id: "streak_30", label: "30-day streak", icon: Trophy, earned: streak30, real: true, tip: streak30 ? "30-day streak" : `30-day streak · ${Math.max(0, 30 - streak)} to go` },
    { id: "monsoon", label: "Monsoon survivor", icon: CloudRain, earned: false, real: false, tip: "Monsoon survivor · locked" },
    { id: "diwali", label: "Diwali shield", icon: Sparkle, earned: false, real: false, tip: "Diwali shield · locked" },
  ];
}
