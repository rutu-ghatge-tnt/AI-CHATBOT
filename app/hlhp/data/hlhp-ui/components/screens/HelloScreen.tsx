"use client";

import { useEffect, useRef, useState } from "react";
import {
  MoveRight, Sparkles, Smile, ShieldHalf, AlertTriangle, Flame, Siren,
  Sun, SunMedium, Droplet, Wind, ChevronDown, Lightbulb,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHlhp } from "@/lib/store";
import type { ImpactDriver } from "@/api/types";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { DriftParticles } from "@/components/anim/Particles";
import { Mascot } from "@/components/anim/Mascot";
import { useReplay, useCountUp } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/**
 * S0 — Hello (v2, enhanced). Folds in the old Surge tab.
 *  • animated SFI score: count-up + ring sweep, color by band
 *  • mode badge (Smooth Sailing → … → Hostile Mode → Code Red)
 *  • L0 compact flash alert → tap to expand L1 + actionable tip
 *  • impact lines: Temp/UV/Humidity/AQI as Low/Medium/High (driver colors)
 *  • "Simulate sudden surge" demo toggle (force_surge) → Hostile Mode + shake
 */

const MODE_ICON: Record<string, LucideIcon> = {
  "Paradise Mode": Sparkles,
  "Smooth Sailing": Smile,
  "Guard Up": ShieldHalf,
  "Battle Stations": AlertTriangle,
  "Hostile Mode": Flame,
  "Code Red": Siren,
};
const MODE_STYLE: Record<string, { col: string; bg: string }> = {
  "Paradise Mode": { col: "var(--accent-tertiary-dark)", bg: "var(--accent-tertiary-light)" },
  "Smooth Sailing": { col: "var(--accent-primary-dark)", bg: "var(--accent-primary-light)" },
  "Guard Up": { col: "var(--accent-secondary-dark)", bg: "var(--accent-secondary-light)" },
  "Battle Stations": { col: "var(--drv-temp)", bg: "color-mix(in oklch,var(--drv-temp) 16%,white)" },
  "Hostile Mode": { col: "var(--destructive)", bg: "color-mix(in oklch,var(--destructive) 14%,white)" },
  "Code Red": { col: "var(--destructive)", bg: "color-mix(in oklch,var(--destructive) 20%,white)" },
};
const DRIVER_META: Record<ImpactDriver, { icon: LucideIcon; col: string }> = {
  temp: { icon: SunMedium, col: "var(--drv-temp)" },
  uv: { icon: Sun, col: "var(--drv-uv)" },
  humidity: { icon: Droplet, col: "var(--drv-humidity)" },
  aqi: { icon: Wind, col: "var(--drv-aqi)" },
};
function ringColor(sfi: number) {
  if (sfi >= 70) return "var(--accent-tertiary-dark)";
  if (sfi >= 55) return "var(--accent-primary)";
  if (sfi >= 40) return "var(--drv-temp)";
  return "var(--destructive)";
}
function confColor(c: string) {
  return c === "HIGH" ? "var(--accent-tertiary-dark)" : c === "MODERATE" ? "var(--accent-primary-dark)" : "var(--muted-foreground)";
}
const LEVEL_PCT: Record<string, number> = { Low: 33, Medium: 66, High: 100 };

export function HelloScreen() {
  const { scan, surge, setSurge, setTab, sfx } = useHlhp();
  const [rk, replay] = useReplay();
  const [alertOpen, setAlertOpen] = useState(false);
  const [ringLen, setRingLen] = useState(0);
  const [impactShown, setImpactShown] = useState(false);
  const [badgeIn, setBadgeIn] = useState(false);
  const [alertIn, setAlertIn] = useState(false);

  const sfi = scan?.sfi ?? 0;
  const mode = scan?.flash_alert.mode ?? scan?.band ?? "Smooth Sailing";
  const ModeIcon = MODE_ICON[mode] ?? Smile;
  const modeStyle = MODE_STYLE[mode] ?? MODE_STYLE["Smooth Sailing"];
  const alert = scan?.flash_alert;
  const impacts = scan?.impacts ?? [];
  const cell = scan?.evidence_cell;

  const R = 80;
  const C = 2 * Math.PI * R;
  const num = useCountUp(sfi, 1500, rk);

  // entrance sequence (also on replay / surge change)
  useEffect(() => {
    setAlertOpen(false);
    setBadgeIn(false);
    setAlertIn(false);
    setImpactShown(false);
    setRingLen(0);
    const t0 = setTimeout(() => setRingLen((C * sfi) / 100), 250);
    const t1 = setTimeout(() => setBadgeIn(true), 700);
    const t2 = setTimeout(() => setAlertIn(true), 450);
    const t3 = setTimeout(() => setImpactShown(true), 600);
    // surge: shake the frame + alert sfx
    if (surge) {
      const frame = document.getElementById("hlhp-frame");
      if (frame) {
        frame.style.animation = "none";
        void frame.offsetWidth;
        frame.style.animation = "shake 0.5s cubic-bezier(.36,.07,.19,.97)";
      }
      const ta = setTimeout(() => sfx("alert"), 200);
      return () => [t0, t1, t2, t3, ta].forEach(clearTimeout);
    }
    return () => [t0, t1, t2, t3].forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rk, sfi, surge]);

  function toggleAlert() {
    setAlertOpen((o) => !o);
    sfx(alertOpen ? "tap" : "pop");
  }

  return (
    <Screen
      stageClassName={cn(
        surge
          ? "bg-[linear-gradient(180deg,color-mix(in_oklch,var(--destructive)_14%,transparent),color-mix(in_oklch,var(--drv-temp)_8%,transparent)_45%,transparent_75%)]"
          : "bg-[linear-gradient(180deg,color-mix(in_oklch,var(--accent-primary)_16%,transparent),color-mix(in_oklch,var(--accent-secondary)_10%,transparent)_40%,transparent_70%)]"
      )}
    >
      <DriftParticles count={10} color={surge ? "var(--destructive)" : "var(--accent-primary-dark)"} />
      {!surge && (
        <svg className="absolute right-5 top-4" width="52" height="52" viewBox="0 0 80 80" style={{ animation: "sunRotate 28s linear infinite" }} aria-hidden="true">
          <circle cx="40" cy="40" r="20" fill="var(--accent-secondary)" />
          <g stroke="var(--accent-primary)" strokeWidth="3" strokeLinecap="round">
            <line x1="40" y1="6" x2="40" y2="14" /><line x1="40" y1="66" x2="40" y2="74" />
            <line x1="6" y1="40" x2="14" y2="40" /><line x1="66" y1="40" x2="74" y2="40" />
            <line x1="16" y1="16" x2="22" y2="22" /><line x1="58" y1="58" x2="64" y2="64" />
            <line x1="64" y1="16" x2="58" y2="22" /><line x1="22" y1="58" x2="16" y2="64" />
          </g>
        </svg>
      )}

      <div className="relative z-[2]">
        <ReplayBar
          label={`${scan?.city ?? "Baner"} · ${scan ? new Date(scan.date).toLocaleDateString("en-IN", { day: "numeric", month: "long" }) : ""}`}
          onReplay={replay}
        />

        <div className="text-center" key={`greet-${rk}`}>
          <div
            className="mx-auto inline-block overflow-hidden whitespace-nowrap font-holiday text-[22px] font-medium text-primary"
            style={{ animation: "typewriter 1100ms steps(20) 250ms both" }}
          >
            Good morning, {scan?.name ?? "there"}
          </div>
          <div>
            <span
              className="mt-2 inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition-all"
              style={{
                background: modeStyle.bg,
                color: modeStyle.col,
                transform: badgeIn ? "scale(1)" : "scale(0.8)",
                opacity: badgeIn ? 1 : 0,
                transitionTimingFunction: "var(--spring)",
                transitionDuration: "400ms",
              }}
            >
              <ModeIcon className="size-3.5" /> {mode}
            </span>
          </div>
        </div>

        {/* animated SFI ring */}
        <div className="relative mx-auto mt-3.5 size-[184px]">
          <div
            className="pointer-events-none absolute inset-[18px] rounded-full"
            style={{ animation: surge ? "pulseGlowRed 2s ease-in-out infinite" : "pulseGlow 3s ease-in-out infinite" }}
          />
          <svg className="size-full -rotate-90" viewBox="0 0 184 184">
            <circle cx="92" cy="92" r={R} fill="none" stroke="var(--muted)" strokeWidth="12" />
            <circle
              cx="92" cy="92" r={R} fill="none" strokeWidth="12" strokeLinecap="round"
              stroke={ringColor(sfi)}
              strokeDasharray={`${ringLen} 999`}
              style={{ transition: "stroke-dasharray 1500ms var(--spring), stroke 600ms ease" }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <div className="text-[54px] font-bold leading-none text-primary">{num}</div>
            <div className="mt-0.5 text-[13px] text-muted-foreground">SFI / 100</div>
          </div>
          <Mascot mood={sfi < 55 ? "concerned" : "happy"} worried={sfi < 55} size={56} className="absolute -bottom-1.5 left-1/2 -translate-x-1/2" />
        </div>

        {/* L0 alert → expand L1 + tip */}
        {alert && (
          <button
            onClick={toggleAlert}
            className={cn(
              "mt-4 block w-full rounded-2xl border border-border bg-card p-3.5 text-left shadow-sm transition-all hover:shadow-md",
              alertOpen && "ring-1 ring-border"
            )}
            style={{
              opacity: alertIn ? 1 : 0,
              transform: alertIn ? "translateY(0)" : "translateY(14px)",
              transition: "opacity 500ms var(--spring), transform 500ms var(--spring)",
            }}
          >
            <div className="flex items-start gap-2.5">
              <div
                className="flex size-[34px] shrink-0 items-center justify-center rounded-[11px]"
                style={{ background: MODE_STYLE[mode]?.bg }}
              >
                <ModeIcon className="size-[18px]" style={{ color: MODE_STYLE[mode]?.col }} />
              </div>
              <div className="flex-1">
                <div className="text-[13.5px] font-medium leading-snug text-primary">{alert.l0}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[10px] text-muted-foreground">
                  <span>{surge ? "Sudden-event · L1" : "Flash alert · L0"}</span>
                  {cell ? (
                    <>
                      <span>· {cell.factor} {cell.band}</span>
                      <span>·</span>
                      <span style={{ color: confColor(cell.confidence) }} className="font-semibold">{cell.confidence}</span>
                      {cell.evidence && <span>· {cell.evidence.split("·")[0].trim()}</span>}
                    </>
                  ) : (
                    <span>· {mode}</span>
                  )}
                </div>
              </div>
              <ChevronDown
                className="ml-auto size-4 text-muted-foreground transition-transform"
                style={{ transform: alertOpen ? "rotate(180deg)" : "none", transitionDuration: "300ms" }}
              />
            </div>
            <div
              className="overflow-hidden"
              style={{ maxHeight: alertOpen ? 320 : 0, marginTop: alertOpen ? 12 : 0, transition: "max-height 420ms var(--spring), margin 420ms var(--spring)" }}
            >
              <div className="border-t border-border pt-3 text-[12px] leading-relaxed text-secondary-foreground">{alert.l1}</div>
              <div className="mt-2.5 flex items-start gap-2 rounded-[10px] bg-accent-tertiary-light p-2.5">
                <Lightbulb className="mt-0.5 size-[15px] text-accent-tertiary-dark" />
                <div className="text-[11.5px] leading-snug text-primary">{alert.tip}</div>
              </div>
              {cell && cell.pmids.length > 0 && (
                <div className="mt-2 text-[9px] leading-relaxed text-muted-foreground">
                  <span className="font-semibold">Evidence:</span> {cell.id} · {cell.pmids.slice(0, 3).join(" · ")}
                </div>
              )}
            </div>
          </button>
        )}

        {/* impact lines */}
        <div className="mt-4">
          <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            What&apos;s pressing on your skin today
          </div>
          {impacts.map((im, i) => {
            const meta = DRIVER_META[im.driver];
            const Icon = meta.icon;
            return (
              <div key={im.driver} className="mb-2.5 flex items-center gap-2.5">
                <div className="flex size-6 shrink-0 items-center justify-center rounded-[7px] text-white" style={{ background: meta.col }}>
                  <Icon className="size-3.5" />
                </div>
                <div className="w-[74px] shrink-0 text-[12px] text-primary">{im.name}</div>
                <div className="relative h-[7px] flex-1 overflow-hidden rounded bg-muted">
                  <div
                    className="h-full rounded"
                    style={{ background: meta.col, width: impactShown ? `${LEVEL_PCT[im.level]}%` : 0, transition: `width 1000ms var(--spring) ${i * 120}ms` }}
                  />
                </div>
                <div className="w-[54px] shrink-0 text-right text-[10px] font-semibold" style={{ color: meta.col }}>{im.level}</div>
              </div>
            );
          })}
        </div>

        <div className="text-center">
          <button
            onClick={() => { sfx("tap"); setTab("s1"); }}
            className="mt-4 inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-[13px] font-medium text-primary-foreground shadow-[0_8px_24px_rgba(26,43,71,0.2)]"
          >
            <MoveRight className="size-4" /> Log how your skin feels
          </button>
        </div>

        {/* demo surge toggle */}
        <div className="mt-3.5 flex items-center justify-center gap-2 rounded-xl border border-border bg-card/70 px-3 py-2 text-[11px] text-muted-foreground">
          Demo:
          <button
            onClick={() => { sfx("tap"); setSurge(!surge); }}
            className={cn("rounded-full px-3 py-1 font-medium transition-colors", surge ? "bg-destructive text-destructive-foreground" : "bg-muted text-primary")}
          >
            {surge ? "Surge ON — reset" : "Simulate sudden surge"}
          </button>
        </div>
      </div>
    </Screen>
  );
}
