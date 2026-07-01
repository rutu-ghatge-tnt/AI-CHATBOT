"use client";

import { useEffect } from "react";
import { Trophy } from "lucide-react";
import { useHlhp } from "@/lib/store";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { EmberParticles } from "@/components/anim/Particles";
import { useReplay, useShowOnMount, useCountUp } from "@/lib/hooks";
import { dayOfMonthFromKey } from "@/lib/dates";
import { streakCountStyle, streakDotStyle } from "@/lib/streakStyles";
import { cn } from "@/lib/utils";

/**
 * S2 — Streak. week_grid from GET /api/hlhp/streak.
 * Inline green/red styles so Skintruth embed cannot strip Tailwind tokens.
 */
export function StreakScreen() {
  const { streakData, refreshStreak } = useHlhp();
  const [rk, replay] = useReplay();
  const show = useShowOnMount(120, rk);

  useEffect(() => {
    refreshStreak();
  }, [refreshStreak, rk]);

  const streak = streakData?.current_streak ?? 0;
  const weekGrid = streakData?.week_grid ?? [];
  const toNext = streakData?.days_to_next_badge ?? (streak < 7 ? 7 - streak : streak < 30 ? 30 - streak : 0);
  const displayCount = useCountUp(show ? streak : 0, 900, rk);

  return (
    <Screen stageClassName="bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--hlhp-flame)_22%,transparent),transparent_70%)]">
      <div style={{ animation: "bgBreathe 8s ease-in-out infinite" }} className="absolute inset-0" />
      <EmberParticles count={16} />
      <div className="relative z-[2] text-center">
        <ReplayBar label={`Day ${streak} streak`} onReplay={replay} />

        <div className="relative mx-auto h-[188px] w-[150px]" key={rk}>
          <div
            className="flame-anim absolute inset-0 origin-bottom"
            style={{ animation: "flameFlicker 1.8s ease-in-out infinite" }}
          >
            <div
              className="absolute inset-0 rounded-full"
              style={{ background: "radial-gradient(circle at 50% 70%, color-mix(in oklch, var(--hlhp-flame) 50%, transparent), transparent 60%)" }}
            />
            <svg width="150" height="188" viewBox="0 0 160 200" className="relative z-[1]" aria-hidden="true">
              <path d="M 80 180 Q 30 150 40 100 Q 50 70 65 80 Q 60 50 80 30 Q 100 50 95 80 Q 110 70 120 100 Q 130 150 80 180 Z" fill="var(--hlhp-flame-mid)" opacity="0.95" />
              <path d="M 80 175 Q 45 150 55 110 Q 65 85 80 90 Q 80 65 95 95 Q 110 110 115 150 Q 105 170 80 175 Z" fill="var(--hlhp-flame)" />
              <path d="M 80 170 Q 60 155 65 130 Q 75 110 80 115 Q 85 105 95 130 Q 100 155 80 170 Z" fill="var(--hlhp-flame-core)" />
            </svg>
          </div>
          <div
            className="pointer-events-none absolute inset-x-0 bottom-[26px] z-[3] flex justify-center"
            aria-label={`${streak} day streak`}
          >
            <span className="hlhp-streak-count" data-streak-count style={streakCountStyle}>
              {displayCount}
            </span>
          </div>
        </div>

        <div className={cn("fade mt-[-6px] text-[12px] font-medium uppercase tracking-wider text-muted-foreground", show && "show")}>
          days strong
        </div>

        <div className="day-grid mt-4 grid grid-cols-7 gap-2" key={`grid-${rk}`}>
          {weekGrid.map((d, i) => (
            <div
              key={d.date}
              className={cn(
                "day-dot hlhp-streak-dot",
                d.done ? "done" : "missed",
                d.today && "today"
              )}
              data-hlhp-day-dot
              data-done={d.done ? "true" : "false"}
              data-today={d.today ? "true" : "false"}
              style={{
                ...streakDotStyle(d.done, !!d.today),
                animation: `dotPop 400ms var(--spring) ${i * 60}ms both`,
              }}
            >
              {dayOfMonthFromKey(d.date)}
            </div>
          ))}
        </div>

        <div
          className={cn("fade mt-4 rounded-xl border border-hlhp-flame/40 p-3.5", show && "show")}
          style={{
            background: "linear-gradient(90deg, color-mix(in oklch, var(--hlhp-flame) 18%, white), color-mix(in oklch, var(--hlhp-flame-core) 14%, white), color-mix(in oklch, var(--hlhp-flame) 18%, white))",
            backgroundSize: "200% 100%",
            animation: "shimmer 3s ease infinite",
          }}
        >
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
