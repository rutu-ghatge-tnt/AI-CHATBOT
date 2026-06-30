"use client";

import { useEffect, useState } from "react";
import { ThermometerSun, Droplet, Wind } from "lucide-react";
import { useHlhp } from "@/lib/store";
import hlhpClient, { ENV } from "@/api/hlhpClient";
import type { CatchupResponse } from "@/api/types";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { Confetti } from "@/components/anim/Particles";
import { useReplay, useStagger } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/**
 * S4 — Recap. /history trend → each day coloured by its DRIVER (humidity=blue,
 * UV=red, heat=orange, AQI=purple, comfort=green) with a legend. /catchup →
 * verdict + driver-coded callouts. Animations: day-mark stagger, walker walk,
 * callout cardBounce, stamp confetti.
 */
const DRIVER_COLOR: Record<string, string> = {
  comfort: "var(--drv-comfort)",
  humidity: "var(--drv-humidity)",
  uv: "var(--drv-uv)",
  temp: "var(--drv-temp)",
  aqi: "var(--drv-aqi)",
};
function colorForDay(d: { sfi: number | null; driver?: string }): string {
  if (d.sfi == null) return "var(--muted)";
  return DRIVER_COLOR[d.driver ?? "comfort"] ?? "var(--drv-comfort)";
}
const LEGEND = [
  { k: "comfort", label: "Comfort" },
  { k: "humidity", label: "Humidity" },
  { k: "uv", label: "UV" },
  { k: "temp", label: "Heat" },
  { k: "aqi", label: "AQI" },
];

export function RecapScreen() {
  const { history } = useHlhp();
  const [rk, replay] = useReplay();
  const [catchupData, setCatchup] = useState<CatchupResponse | null>(null);

  const trend = history?.trend ?? [];
  const [marksShown, setMarksShown] = useState<number>(0);
  const [walkerLeft, setWalkerLeft] = useState(8);
  const [callouts, setCallouts] = useState<boolean[]>([false, false, false]);
  const [stampIn, setStampIn] = useState(false);

  useEffect(() => {
    hlhpClient.catchup(ENV.userId).then(setCatchup);
  }, []);

  // day-mark stagger
  useStagger(trend.length, 26, (i) => setMarksShown(i + 1), 100, [rk, trend.length]);

  // walker walk + callouts + stamp sequence
  useEffect(() => {
    setMarksShown(0);
    setWalkerLeft(8);
    setCallouts([false, false, false]);
    setStampIn(false);
    const w = setTimeout(() => setWalkerLeft(88), 200); // CSS transition 8s
    const c1 = setTimeout(() => setCallouts([true, false, false]), 900);
    const c2 = setTimeout(() => setCallouts([true, true, false]), 1300);
    const c3 = setTimeout(() => setCallouts([true, true, true]), 1700);
    const st = setTimeout(() => setStampIn(true), 2200);
    return () => [w, c1, c2, c3, st].forEach(clearTimeout);
  }, [rk]);

  const events = history?.sudden_events ?? [];
  const fmt = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

  return (
    <Screen stageClassName="bg-[linear-gradient(135deg,color-mix(in_oklch,var(--hlhp-warmth)_12%,transparent),color-mix(in_oklch,var(--accent-primary)_10%,transparent))]">
      <div style={{ animation: "bgBreathe 10s ease-in-out infinite" }} className="absolute inset-0" />
      <div className="relative z-[2]" key={rk}>
        <ReplayBar label="June at a glance" onReplay={replay} />

        <div className="text-center">
          <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Your last 30 days</div>
          <div className="mt-1 text-[20px] font-medium text-primary">
            {trend.length} days · {events.length} surge{events.length === 1 ? "" : "s"} · streak intact
          </div>
        </div>

        {/* legend */}
        <div className="mt-2.5 flex flex-wrap justify-center gap-x-3 gap-y-2">
          {LEGEND.map((l) => (
            <div key={l.k} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className="size-2.5 rounded-[3px]" style={{ background: DRIVER_COLOR[l.k] }} />
              {l.label}
            </div>
          ))}
        </div>

        {/* track + walker */}
        <div className="relative mt-3.5 h-20">
          <div className="absolute bottom-[34px] z-[3]" style={{ left: `${walkerLeft}%`, transition: "left 8s linear", animation: "walk 0.6s ease-in-out infinite" }}>
            <svg width="28" height="36" viewBox="0 0 36 44" aria-hidden="true">
              <ellipse cx="18" cy="26" rx="13" ry="11" fill="#FFFFFF" stroke="#E5D9BD" />
              <circle cx="18" cy="14" r="8" fill="#FFFFFF" stroke="#E5D9BD" />
              <ellipse cx="14" cy="16" rx="3" ry="4" fill="#3F3530" />
              <ellipse cx="22" cy="16" rx="3" ry="4" fill="#3F3530" />
            </svg>
          </div>
          <div className="absolute bottom-2 left-0 right-0 flex gap-[3px] px-2">
            {trend.map((d, i) => (
              <div
                key={d.date}
                className={cn("h-[26px] flex-1 rounded", i < marksShown ? "opacity-100" : "translate-y-2 opacity-0")}
                style={{ background: colorForDay(d), opacity: d.sfi == null ? 0.4 : undefined, transition: "all 400ms ease" }}
              />
            ))}
          </div>
        </div>

        {/* callouts — colour-coded by driver */}
        <Callout show={callouts[0]} accent="var(--drv-temp)" icon={<ThermometerSun className="size-4" style={{ color: "var(--drv-temp)" }} />}>
          <b>{events[0] ? fmt(events[0].date) : "Jun 12"}</b> · Heat wave — SFI {events[0]?.from ?? 78} → {events[0]?.to ?? 54} · you handled it
        </Callout>
        <Callout show={callouts[1]} accent="var(--drv-humidity)" icon={<Droplet className="size-4" style={{ color: "var(--drv-humidity)" }} />}>
          <b>{events[1] ? fmt(events[1].date) : "Jun 19"}</b> · Humidity wave — barrier-stress for a few days
        </Callout>
        <Callout show={callouts[2]} accent="var(--drv-aqi)" icon={<Wind className="size-4" style={{ color: "var(--drv-aqi)" }} />}>
          <b>Jun 24</b> · Dust spike — AQI 210, dull-skin days
        </Callout>

        {/* stamp */}
        <div className="relative mt-2.5 overflow-hidden rounded-2xl bg-primary p-3.5 text-primary-foreground" style={stampIn ? { animation: "cardBounce 800ms var(--spring) both" } : { opacity: 0 }}>
          {stampIn && <Confetti runKey={rk} count={28} />}
          <div className="relative flex items-center justify-between">
            <div>
              <div className="text-[10px] font-medium uppercase tracking-wider text-hlhp-sun">Your June verdict</div>
              <div className="mt-0.5 text-[16px] font-medium">{catchupData?.verdict_headline ?? "Stronger than May"}</div>
              <div className="mt-0.5 text-[11px] text-primary-foreground/70">{catchupData?.verdict_sub ?? "Avg SFI 68 · 0 dropped days"}</div>
            </div>
            <div className="cursor-pointer rounded-full border border-hlhp-sun px-2.5 py-1 text-[10px] text-hlhp-sun">Share</div>
          </div>
        </div>
      </div>
    </Screen>
  );
}

function Callout({ show, icon, accent, children }: { show: boolean; icon: React.ReactNode; accent?: string; children: React.ReactNode }) {
  return (
    <div
      className="mt-2 rounded-xl border border-l-[3px] border-border bg-card px-3.5 py-2.5 text-[12px] text-primary"
      style={{ borderLeftColor: accent, opacity: show ? 1 : 0, transform: show ? "translateY(0) scale(1)" : "translateY(8px) scale(0.95)", transition: "all 500ms var(--spring)" }}
    >
      <div className="flex items-center gap-2">{icon}<span>{children}</span></div>
    </div>
  );
}
