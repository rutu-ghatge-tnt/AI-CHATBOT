"use client";

import { useEffect, useState } from "react";
import { Lightbulb, BellRing, Moon, Shield } from "lucide-react";
import { useHlhp } from "@/lib/store";
import hlhpClient from "@/api/hlhpClient";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { useReplay } from "@/lib/hooks";
import { INSIGHT_CARDS, TIMELINE_PATTERN, WEEK_PATTERN, HOUR_PATTERN, HOUR_SPIKE_INDEXES } from "@/mock/patterns";
import { cn } from "@/lib/utils";

/**
 * SP — Patterns. Card BODIES come from /symptom_explainer (top symptoms from
 * history feelings). Ribbon % + mini-charts are decorative (mock/patterns.ts).
 * Animations: hero + card stagger, timeline dots, correlation bar width,
 * weekday/weekend grid pop, hour-bar scaleY.
 */
const RIBBON_BG: Record<string, string> = {
  insight: "linear-gradient(135deg, var(--primary), var(--accent-primary-dark))",
  good: "linear-gradient(135deg, var(--hlhp-good-deep), var(--hlhp-good))",
  warmth: "linear-gradient(135deg, var(--hlhp-warmth-deep), var(--destructive))",
};
const CTA_ICON: Record<string, React.ReactNode> = {
  humidity_surge: <BellRing className="size-3.5" />,
  sleep: <Moon className="size-3.5" />,
  shield: <Shield className="size-3.5" />,
};

export function PatternsScreen() {
  const { history } = useHlhp();
  const [rk, replay] = useReplay();
  const [shown, setShown] = useState(0);
  const [bodies, setBodies] = useState<Record<string, string>>({});

  // pick top symptoms from history, pull explainer bodies (real-shaped call)
  useEffect(() => {
    const top = Object.entries(history?.feelings ?? {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([k]) => k);
    const keys = top.length ? top : ["itchy", "dry", "breakout"];
    Promise.all(keys.map((k) => hlhpClient.symptomExplainer(k))).then((res) => {
      const map: Record<string, string> = {};
      res.forEach((r) => (map[r.keyword] = r.sections[1]?.body ?? r.sections[0]?.body ?? ""));
      setBodies(map);
    });
  }, [history]);

  // stagger hero(0) + 3 cards
  useEffect(() => {
    setShown(0);
    const timers = [0, 1, 2, 3].map((i) => setTimeout(() => setShown((s) => Math.max(s, i + 1)), 150 + i * 180));
    return () => timers.forEach(clearTimeout);
  }, [rk]);

  const nLogs = history?.daily_logs.length ?? 0;

  return (
    <Screen stageClassName="before:absolute before:inset-0 before:bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--primary)_8%,transparent),transparent_70%)] before:content-['']">
      <div className="relative z-[2]" key={rk}>
        <ReplayBar label="Your skin patterns" onReplay={replay} />

        {/* hero */}
        <div
          className="mb-3 rounded-2xl bg-gradient-to-br from-primary to-accent-primary-dark p-3.5 text-white"
          style={{ opacity: shown >= 1 ? 1 : 0, transform: shown >= 1 ? "translateY(0) scale(1)" : "translateY(20px) scale(0.95)", transition: "all 600ms var(--spring)" }}
        >
          <div className="flex items-start justify-between gap-2.5">
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider opacity-80">We noticed</div>
              <div className="mt-0.5 text-[15px] font-medium">
                {INSIGHT_CARDS.length} patterns in your last {Math.max(nLogs * 6, 47)} logs
              </div>
            </div>
            <Lightbulb className="size-6 text-hlhp-sun" />
          </div>
        </div>

        {/* insight cards */}
        {INSIGHT_CARDS.map((card, idx) => (
          <div
            key={card.id}
            className="relative mb-2.5 rounded-2xl border border-border bg-card p-3.5"
            style={{ opacity: shown >= idx + 2 ? 1 : 0, transform: shown >= idx + 2 ? "translateY(0) scale(1)" : "translateY(30px) scale(0.9)", transition: "all 700ms var(--spring)" }}
          >
            <div className="absolute right-0 top-0 rounded-bl-xl rounded-tr-2xl px-2.5 py-0.5 text-[10px] font-semibold text-white" style={{ background: RIBBON_BG[card.ribbonColor] }}>
              {card.matchPct}% match
            </div>
            <div className="pr-16 text-[13px] font-semibold text-primary">{card.title}</div>

            {card.chart === "timeline" && <TimelineChart active={shown >= idx + 2} />}
            {card.chart === "weekgrid" && <WeekGrid active={shown >= idx + 2} />}
            {card.chart === "hours" && <HourChart active={shown >= idx + 2} />}

            <div className="text-[11px] leading-relaxed text-muted-foreground">
              {bodies[card.id] ?? card.body}
            </div>
            <button className="mt-1.5 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-medium text-white" style={{ background: card.ribbonColor === "good" ? "var(--hlhp-good-deep)" : card.ribbonColor === "warmth" ? "var(--hlhp-warmth-deep)" : "var(--accent-primary-dark)" }}>
              {CTA_ICON[card.ctaTag]} {card.ctaLabel}
            </button>
          </div>
        ))}
      </div>
    </Screen>
  );
}

function TimelineChart({ active }: { active: boolean }) {
  const [w, setW] = useState(0);
  useEffect(() => { const t = setTimeout(() => setW(active ? 83 : 0), 200); return () => clearTimeout(t); }, [active]);
  return (
    <>
      <div className="my-2 flex h-7 gap-[3px]">
        {TIMELINE_PATTERN.map((v, i) => (
          <div
            key={i}
            className={cn("flex-1 rounded-[3px] origin-bottom", v === 1 ? "bg-gradient-to-b from-destructive to-hlhp-surge-deep" : v === 2 ? "bg-gradient-to-b from-accent-primary to-accent-primary-dark" : "bg-muted")}
            style={{ transform: active ? "scaleY(1)" : "scaleY(0)", transition: `transform 600ms var(--spring) ${i * 30}ms` }}
          />
        ))}
      </div>
      <div className="my-1.5 h-1.5 overflow-hidden rounded-[3px] bg-muted">
        <div className="h-full rounded-[3px] bg-gradient-to-r from-accent-primary to-accent-primary-dark" style={{ width: `${w}%`, transition: "width 1400ms var(--spring)" }} />
      </div>
    </>
  );
}

function WeekGrid({ active }: { active: boolean }) {
  return (
    <div className="my-2 grid grid-cols-7 gap-1">
      {WEEK_PATTERN.map((weekend, i) => (
        <div
          key={i}
          className={cn("flex aspect-square items-center justify-center rounded-md text-[10px]", weekend ? "bg-gradient-to-br from-hlhp-good to-hlhp-good-deep text-white" : "bg-muted text-secondary-foreground")}
          style={{ transform: active ? "scale(1)" : "scale(0)", transition: `transform 500ms var(--spring) ${i * 50}ms` }}
        >
          {["M", "T", "W", "T", "F", "S", "S"][i]}
        </div>
      ))}
    </div>
  );
}

function HourChart({ active }: { active: boolean }) {
  return (
    <div className="my-2 flex h-11 items-end gap-[3px]">
      {HOUR_PATTERN.map((h, i) => (
        <div
          key={i}
          className={cn("flex-1 rounded-t-[3px] origin-bottom", HOUR_SPIKE_INDEXES.includes(i) ? "bg-gradient-to-b from-destructive to-hlhp-surge-deep" : "bg-gradient-to-b from-accent-primary to-accent-primary-dark")}
          style={{ height: `${h}%`, transform: active ? "scaleY(1)" : "scaleY(0)", transition: `transform 500ms var(--spring) ${i * 40}ms` }}
        />
      ))}
    </div>
  );
}
