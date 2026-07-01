"use client";

import { useEffect, useState } from "react";
import { useHlhp } from "@/lib/store";
import { COACH_BY_TAB } from "@/lib/tabs";
import { cn } from "@/lib/utils";

/**
 * Coach bubble — screen-specific message. Hello/Streak/Surge prefer live copy
 * from scan.alerts[0].coach_wrap; the rest use the static map. Slides in on
 * each tab change (spring easing, ported from the prototype .coach-bubble).
 */
export function CoachBubble() {
  const { tab, scan, streak } = useHlhp();
  const [show, setShow] = useState(false);

  const wrap = scan?.alerts?.[0]?.coach_wrap;
  const streakMsg =
    streak >= 1
      ? `Day ${streak} of showing up. Your skin notices the consistency.`
      : undefined;
  const live: Partial<Record<string, string | undefined>> = {
    s0: scan?.sudden_event_tags.length ? wrap?.l2 : wrap?.forward_hook ?? wrap?.greeting,
    s2: streakMsg ?? wrap?.effort_recognition,
  };
  const meta = COACH_BY_TAB[tab];
  const msg = live[tab] ?? meta.fallback;

  // re-animate on tab/message change
  useEffect(() => {
    setShow(false);
    const t = setTimeout(() => setShow(true), 60);
    return () => clearTimeout(t);
  }, [tab, msg]);

  return (
    <div
      className={cn(
        "relative mx-4 mt-2.5 flex items-start gap-2.5 rounded-2xl px-3.5 py-2.5 text-primary-foreground shadow-[0_4px_14px_rgba(82,64,166,0.18)] transition-all",
        "bg-gradient-to-br from-primary to-accent-primary-dark",
        show ? "translate-y-0 opacity-100" : "-translate-y-2.5 opacity-0"
      )}
      style={{ transitionTimingFunction: "var(--spring)", transitionDuration: "500ms" }}
    >
      {/* speech-tail */}
      <span className="absolute -top-1.5 left-6 size-3 rotate-45 bg-primary" />
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-hlhp-sun to-hlhp-warmth text-[11px] font-bold text-primary">
        C
      </span>
      <div className="text-[12px] leading-snug">
        <span className="mb-0.5 block text-[9px] font-semibold uppercase tracking-wider text-hlhp-sun">
          {meta.tag}
        </span>
        {msg}
      </div>
    </div>
  );
}
