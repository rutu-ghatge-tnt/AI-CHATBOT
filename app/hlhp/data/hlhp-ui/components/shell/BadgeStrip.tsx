"use client";

import { useMemo } from "react";
import { Check } from "lucide-react";
import { useHlhp } from "@/lib/store";
import { computeBadges } from "@/mock/badges";
import { cn } from "@/lib/utils";

/**
 * Badge strip — 4 earned + 3 locked, computed client-side (mock/badges.ts).
 * Earned badges use the warmth ramp; locked are muted with a tooltip.
 */
export function BadgeStrip() {
  const { logCount, streak, history } = useHlhp();
  const hadSuddenEvent = (history?.sudden_events.length ?? 0) > 0;

  const badges = useMemo(
    () => computeBadges({ logCount, streak, hadSuddenEvent }),
    [logCount, streak, hadSuddenEvent]
  );

  return (
    <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto border-b border-border/70 bg-accent-primary/5 px-4 py-2">
      <span className="mr-1.5 whitespace-nowrap text-[9px] font-medium uppercase tracking-wider text-muted-foreground">
        Badges
      </span>
      {badges.map((b) => {
        const Icon = b.icon;
        return (
          <div key={b.id} className="group relative">
            <div
              className={cn(
                "flex size-[26px] items-center justify-center rounded-full transition-transform group-hover:-translate-y-0.5",
                b.earned
                  ? "bg-gradient-to-br from-accent-primary to-accent-primary-dark text-white shadow-sm"
                  : "bg-muted text-muted-foreground"
              )}
            >
              <Icon className="size-3.5" />
              {b.earned && (
                <span className="absolute -bottom-0.5 -right-0.5 flex size-3 items-center justify-center rounded-full border-[1.5px] border-background bg-hlhp-good-deep text-white">
                  <Check className="size-2" strokeWidth={4} />
                </span>
              )}
            </div>
            <span className="pointer-events-none absolute -bottom-7 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-md bg-primary px-2 py-1 text-[10px] text-primary-foreground opacity-0 transition-opacity group-hover:opacity-100">
              {b.tip}
            </span>
          </div>
        );
      })}
    </div>
  );
}
