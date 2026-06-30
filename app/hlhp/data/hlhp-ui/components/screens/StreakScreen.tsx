"use client";

import { useEffect, useState } from "react";
import { Trophy } from "lucide-react";
import { useHlhp } from "@/lib/store";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { EmberParticles } from "@/components/anim/Particles";
import { useReplay, useShowOnMount } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/**
 * S2 — Streak. Number from /history streak (mock). Day-grid derived from
 * history daily_logs (logged days). Flame flicker + ember particles, counter
 * roll-up, dotPop grid stagger, milestone shimmer.
 */
export function StreakScreen() {
  const { streak, history } = useHlhp();
  const [rk, replay] = useReplay();
  const show = useShowOnMount(120, rk);

  // build 7-day window ending today; mark which were logged
  const loggedDates = new Set((history?.daily_logs ?? []).map((l) => l.date));
  const last7 = Array.from({ length: 7 }).map((_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (6 - i));
    const iso = d.toISOString().slice(0, 10);
    const today = i === 6;
    return { iso, day: d.getDate(), done: loggedDates.has(iso) || today, today };
  });

  const tens = Math.floor(streak / 10);
  const ones = streak % 10;
  const toNext = streak < 7 ? 7 - streak : streak < 30 ? 30 - streak : 0;

  return (
    <Screen stageClassName="bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--hlhp-flame)_22%,transparent),transparent_70%)]" >
      <div style={{ animation: "bgBreathe 8s ease-in-out infinite" }} className="absolute inset-0" />
      <EmberParticles count={16} />
      <div className="relative z-[2] text-center">
        <ReplayBar label={`Day ${streak} streak`} onReplay={replay} />

        {/* flame + rolling counter — the one warm-amber moment in the app */}
        <div className="relative mx-auto h-[188px] w-[150px]" style={{ animation: "flameFlicker 1.8s ease-in-out infinite" }} key={rk}>
          <div className="absolute inset-0 rounded-full" style={{ background: "radial-gradient(circle at 50% 70%, color-mix(in oklch, var(--hlhp-flame) 50%, transparent), transparent 60%)" }} />
          <svg width="150" height="188" viewBox="0 0 160 200" className="relative z-[1]" aria-hidden="true">
            <path d="M 80 180 Q 30 150 40 100 Q 50 70 65 80 Q 60 50 80 30 Q 100 50 95 80 Q 110 70 120 100 Q 130 150 80 180 Z" fill="var(--hlhp-flame-mid)" opacity="0.95" />
            <path d="M 80 175 Q 45 150 55 110 Q 65 85 80 90 Q 80 65 95 95 Q 110 110 115 150 Q 105 170 80 175 Z" fill="var(--hlhp-flame)" />
            <path d="M 80 170 Q 60 155 65 130 Q 75 110 80 115 Q 85 105 95 130 Q 100 155 80 170 Z" fill="var(--hlhp-flame-core)" />
          </svg>
          <div className="absolute bottom-[30px] left-1/2 z-[2] flex -translate-x-1/2 items-center">
            <Roller digit={show ? tens : 0} />
            <Roller digit={show ? ones : 0} />
          </div>
        </div>

        <div className={cn("fade mt-[-6px] text-[12px] font-medium uppercase tracking-wider text-muted-foreground", show && "show")}>
          days strong
        </div>

        {/* 7-day grid */}
        <div className="mt-4 grid grid-cols-7 gap-2" key={`grid-${rk}`}>
          {last7.map((d, i) => (
            <div
              key={d.iso}
              className={cn(
                "flex aspect-square items-center justify-center rounded-full text-[10px] font-medium",
                d.today
                  ? "bg-gradient-to-br from-accent-primary-dark to-primary text-white shadow-[0_0_0_4px_color-mix(in_oklch,var(--accent-primary)_20%,transparent)]"
                  : d.done
                  ? "bg-gradient-to-br from-hlhp-flame to-hlhp-flame-mid text-white"
                  : "bg-muted text-transparent"
              )}
              style={{ animation: `dotPop 400ms var(--spring) ${i * 60}ms both` }}
            >
              {d.day}
            </div>
          ))}
        </div>

        {/* milestone */}
        <div className={cn("fade mt-4 rounded-xl border border-hlhp-flame/40 p-3.5", show && "show")} style={{ background: "linear-gradient(90deg, color-mix(in oklch, var(--hlhp-flame) 18%, white), color-mix(in oklch, var(--hlhp-flame-core) 14%, white), color-mix(in oklch, var(--hlhp-flame) 18%, white))", backgroundSize: "200% 100%", animation: "shimmer 3s ease infinite" }}>
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-hlhp-flame-mid text-white">
              <Trophy className="size-4" />
            </div>
            <div className="text-left">
              <div className="text-[12px] font-medium text-primary">
                {toNext > 0 ? `${toNext} days to your ${streak < 7 ? "7" : "30"}-day badge` : "Badge unlocked"}
              </div>
              <div className="mt-0.5 text-[10px] text-muted-foreground">Only 3% of users reach 30 days</div>
            </div>
          </div>
        </div>
      </div>
    </Screen>
  );
}

/** single rolling digit column (0–9), rolls to `digit` with spring easing */
function Roller({ digit }: { digit: number }) {
  const [d, setD] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setD(digit), 80);
    return () => clearTimeout(t);
  }, [digit]);
  return (
    <div className="relative h-9 w-[22px] overflow-hidden">
      <div className="absolute" style={{ transform: `translateY(-${d * 36}px)`, transition: "transform 1200ms var(--spring)" }}>
        {Array.from({ length: 10 }).map((_, n) => (
          <div key={n} className="flex h-9 w-[22px] items-center justify-center text-[32px] font-semibold text-white [text-shadow:0_2px_4px_rgba(0,0,0,0.3)]">
            {n}
          </div>
        ))}
      </div>
    </div>
  );
}
