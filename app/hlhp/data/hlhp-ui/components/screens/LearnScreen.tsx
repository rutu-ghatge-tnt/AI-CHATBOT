"use client";

import { useEffect, useState } from "react";
import { Activity, Droplet, Wind, SunMedium, BookOpen, Clock } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHlhp } from "@/lib/store";
import hlhpClient, { ENV } from "@/api/hlhpClient";
import type { LearnFeed } from "@/api/types";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { DriftParticles } from "@/components/anim/Particles";
import { useReplay } from "@/lib/hooks";

/**
 * SL — Learn (v2, replaces Good Day). Two sections:
 *  1. "Why your skin felt that" — symptom explainers (from /v2 explainers)
 *  2. "From the SkinBB evidence base" — REAL Did-You-Know nuggets from the
 *     scenario library, surfaced by today's dominant driver. Educational, plain
 *     language, cited, no product recommendations.
 */
// dominant impact driver → the library's factor name used by nuggets
const DRIVER_TO_FACTOR: Record<string, string> = {
  temp: "Temperature", uv: "UV", humidity: "Humidity", aqi: "AQI",
};
const FACTOR_META: Record<string, { icon: LucideIcon; col: string }> = {
  Temperature: { icon: SunMedium, col: "var(--drv-temp)" },
  UV: { icon: SunMedium, col: "var(--drv-uv)" },
  Humidity: { icon: Droplet, col: "var(--drv-humidity)" },
  AQI: { icon: Wind, col: "var(--drv-aqi)" },
  Pollution: { icon: Wind, col: "var(--drv-aqi)" },
  Nutrition: { icon: BookOpen, col: "var(--accent-tertiary-dark)" },
};

export function LearnScreen() {
  const { surge, scan, sfx, evidence } = useHlhp();
  const [rk, replay] = useReplay();
  const [feed, setFeed] = useState<LearnFeed | null>(null);
  const [shown, setShown] = useState(0);

  useEffect(() => {
    hlhpClient.learn(ENV.userId).then(setFeed);
  }, []);

  // REAL Did-You-Know nuggets, dominant driver's factor first
  const domDriver = scan?.impacts.slice().sort((a, b) => {
    const ord = { High: 0, Medium: 1, Low: 2 } as const;
    return ord[a.level] - ord[b.level];
  })[0]?.driver;
  const domFactor = surge ? "Temperature" : DRIVER_TO_FACTOR[domDriver ?? "humidity"] ?? "Humidity";
  const nuggets = (evidence?.nuggets ?? []).slice().sort(
    (a, b) => (a.factor === domFactor || (domFactor === "AQI" && a.factor === "Pollution") ? -1 : 0)
            - (b.factor === domFactor || (domFactor === "AQI" && b.factor === "Pollution") ? -1 : 0)
  ).slice(0, 8);

  // stagger reveal
  const total = (feed?.explainers.length ?? 0) + (nuggets.length || (feed?.articles.length ?? 0));
  useEffect(() => {
    setShown(0);
    if (!feed) return;
    const timers = Array.from({ length: total }).map((_, i) =>
      setTimeout(() => setShown((s) => Math.max(s, i + 1)), 120 + i * 100)
    );
    return () => timers.forEach(clearTimeout);
  }, [feed, rk, total]);

  let idx = 0;

  return (
    <Screen stageClassName="before:absolute before:inset-0 before:bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--accent-primary)_10%,transparent),transparent_70%)] before:content-['']">
      <DriftParticles count={8} color="var(--accent-primary-dark)" />
      <div className="relative z-[2]">
        <ReplayBar label="Learn · tuned to your skin" onReplay={replay} />

        <div className="mb-2 mt-3.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Why your skin felt that
        </div>
        {(feed?.explainers ?? []).map((e) => {
          const i = idx++;
          return (
            <div
              key={e.keyword}
              className="mb-2.5 rounded-2xl border border-border p-3.5"
              style={{
                background: "linear-gradient(135deg, var(--accent-primary-light), color-mix(in oklch, var(--accent-secondary-light) 70%, white))",
                opacity: shown > i ? 1 : 0,
                transform: shown > i ? "translateY(0)" : "translateY(18px)",
                transition: "all 600ms var(--spring)",
              }}
            >
              <div className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider text-accent-primary-dark">
                <Activity className="size-3" /> Because you logged &quot;{e.keyword}&quot;
              </div>
              <div className="mt-1 text-[14px] font-semibold text-primary">{e.title}</div>
              <div className="mt-1 text-[11.5px] leading-relaxed text-secondary-foreground">{e.body}</div>
            </div>
          );
        })}

        <div className="mb-2 mt-3.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          From the SkinBB evidence base · Did you know
        </div>
        {nuggets.map((n) => {
          const i = idx++;
          const meta = FACTOR_META[n.factor] ?? FACTOR_META.Nutrition;
          const Icon = meta.icon;
          return (
            <button
              key={n.n}
              onClick={() => sfx("tap")}
              className="mb-2.5 flex w-full gap-3 rounded-2xl border border-border bg-card p-3 text-left transition-shadow hover:shadow-md"
              style={{
                opacity: shown > i ? 1 : 0,
                transform: shown > i ? "translateY(0)" : "translateY(18px)",
                transition: "all 600ms var(--spring), box-shadow 200ms ease",
              }}
            >
              <div className="flex size-[54px] shrink-0 items-center justify-center rounded-[11px] text-white" style={{ background: meta.col }}>
                <Icon className="size-6" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[9px] font-bold uppercase tracking-wide" style={{ color: meta.col }}>{n.factor} · did you know</div>
                <div className="mt-0.5 text-[11.5px] font-medium leading-snug text-primary">{n.text}</div>
                <div className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Clock className="size-3" /> {n.source}
                </div>
              </div>
            </button>
          );
        })}

        <div onClick={() => sfx("tap")} className="mt-2 cursor-pointer p-2.5 text-center text-[11px] font-semibold text-accent-primary-dark">
          Browse the full library →
        </div>
      </div>
    </Screen>
  );
}
