"use client";

import { useRef, useState } from "react";
import {
  DropletOff, Droplet, Contrast, Spline, CircleDot, Sparkles, Check, Save,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useHlhp } from "@/lib/store";
import hlhpClient, { ENV, USE_MOCK } from "@/api/hlhpClient";
import { Screen, ReplayBar } from "@/components/shell/ScreenShell";
import { DriftParticles } from "@/components/anim/Particles";
import { useReplay } from "@/lib/hooks";
import { cn } from "@/lib/utils";

/**
 * S1 — Log (v2). Chips Dry / Oily / Dull / Breakout / Spots — MULTI-SELECT.
 * Breakout & Spots reveal a multi-select face-area picker (incl. "Full face").
 * One Save button commits all. "Spots" exists because acne often leaves marks.
 */
const CHIPS: { k: string; label: string; icon: LucideIcon }[] = [
  { k: "dry", label: "Dry", icon: DropletOff },
  { k: "oily", label: "Oily", icon: Droplet },
  { k: "dull", label: "Dull", icon: Contrast },
  { k: "breakout", label: "Breakout", icon: Spline },
  { k: "spots", label: "Spots", icon: CircleDot },
];
const AREAS = ["Full face", "Forehead", "Cheeks", "Chin", "Nose", "Jaw"];
const NEEDS_AREA: Record<string, boolean> = { breakout: true, spots: true };
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function LogScreen() {
  const { surge, sfx, bumpLog, refreshStreak } = useHlhp();
  const [rk, replay] = useReplay();
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [areas, setAreas] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [fx, setFx] = useState<{ id: number; x: number; y: number }[]>([]);
  const fxId = useRef(0);

  const syms = Object.keys(picked).filter((k) => picked[k]);
  const areaList = Object.keys(areas).filter((a) => areas[a]);
  const needArea = syms.some((s) => NEEDS_AREA[s]);

  function burst(e: React.MouseEvent) {
    const host = (e.currentTarget as HTMLElement).closest("[data-log-root]") as HTMLElement | null;
    const r = host?.getBoundingClientRect();
    const t = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const x = r ? t.left - r.left + t.width / 2 : 0;
    const y = r ? t.top - r.top + t.height / 2 : 0;
    const id = fxId.current++;
    setFx((f) => [...f, { id, x, y }]);
    setTimeout(() => setFx((f) => f.filter((p) => p.id !== id)), 1600);
  }

  function toggleChip(e: React.MouseEvent, k: string) {
    setSaved(false);
    setPicked((p) => {
      const next = { ...p };
      if (next[k]) { delete next[k]; sfx("tap"); }
      else { next[k] = true; sfx("chip"); burst(e); }
      return next;
    });
  }
  function toggleArea(k: string) {
    sfx("tap");
    setSaved(false);
    setAreas((a) => {
      if (k === "Full face") {
        return a["Full face"] ? {} : { "Full face": true };
      }
      const next = { ...a };
      delete next["Full face"];
      if (next[k]) delete next[k];
      else next[k] = true;
      return next;
    });
  }

  async function save() {
    if (syms.length === 0) return;
    sfx("save");
    setSaved(true);
    bumpLog();
    const localTime = new Date().toISOString();
    const areaSlugs = areaList.map((a) =>
      a === "Full face" ? "full_face" : a.toLowerCase().replace(/\s+/g, "_")
    );
    if (!USE_MOCK) {
      await hlhpClient.userLog({
        user_id: ENV.userId,
        symptoms: syms,
        areas: areaSlugs,
        local_time: localTime,
        location_city: ENV.city,
        latitude: ENV.lat,
        longitude: ENV.lng,
      });
    } else {
      for (const s of syms) {
        await hlhpClient.symptomFeeling({
          user_id: ENV.userId,
          symptom_keyword: s,
          local_time: localTime,
          selected: true,
        });
      }
    }
    await refreshStreak();
    setShowToast(true);
    setTimeout(() => setShowToast(false), 2200);
  }

  const envLine = surge ? "Heat surge · UV 11 · AQI 380" : "Humidity surge +22pts";

  return (
    <Screen stageClassName="before:absolute before:inset-0 before:bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--accent-primary)_10%,transparent),transparent_70%)] before:content-['']">
      <div data-log-root className="relative z-[2]">
        <DriftParticles count={8} color="var(--accent-primary-dark)" />
        <ReplayBar label="How does your skin feel?" onReplay={() => { setPicked({}); setAreas({}); setSaved(false); replay(); }} />

        <div className="mb-1.5 text-[11px] text-muted-foreground">Pick all that apply</div>
        <div key={rk}>
          {CHIPS.map((c) => {
            const Icon = c.icon;
            const on = !!picked[c.k];
            return (
              <button
                key={c.k}
                onClick={(e) => toggleChip(e, c.k)}
                className={cn(
                  "mr-1.5 mt-1.5 inline-flex select-none items-center gap-1.5 rounded-full border px-4 py-2 text-[13px] transition-all hover:-translate-y-0.5",
                  on ? "border-accent-primary bg-accent-primary-light font-medium text-accent-primary-dark" : "border-border bg-card text-primary"
                )}
                style={on ? { animation: "chipPop 480ms var(--spring)" } : undefined}
              >
                <Icon className="size-3.5" /> {c.label}
                {on && <Check className="size-3" strokeWidth={3} />}
              </button>
            );
          })}
        </div>

        {/* face areas (breakout / spots) */}
        {needArea && (
          <div className="mt-3.5 rounded-2xl border border-border bg-card p-4" style={{ animation: "cardBounce 700ms var(--spring) both" }}>
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Where? (breakout / spots)</div>
            <div className="flex flex-wrap gap-1.5">
              {AREAS.map((a) => (
                <button
                  key={a}
                  onClick={() => toggleArea(a)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-[12px] transition-all",
                    a === "Full face" && "border-dashed",
                    areas[a] ? "border-accent-primary bg-accent-primary-light font-semibold text-accent-primary-dark" : "border-border text-primary"
                  )}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* captured panel */}
        {syms.length > 0 && (
          <div className="fade show mt-3.5 rounded-xl bg-accent-primary-light/50 p-3.5">
            <div className="mb-1.5 text-[11px] font-medium tracking-wide text-secondary-foreground">TODAY&apos;S LOG</div>
            <div className="flex justify-between gap-3 py-1 text-[12px]">
              <span className="text-muted-foreground">Feeling</span>
              <span className="text-right font-medium text-accent-primary-dark">{syms.map(cap).join(", ")}</span>
            </div>
            {areaList.length > 0 && (
              <div className="flex justify-between gap-3 py-1 text-[12px]">
                <span className="text-muted-foreground">Where</span>
                <span className="text-right font-medium text-accent-primary-dark">{areaList.join(", ")}</span>
              </div>
            )}
            <div className="flex justify-between gap-3 py-1 text-[12px]">
              <span className="text-muted-foreground">Environment</span>
              <span className="text-right font-medium text-accent-primary-dark">{envLine}</span>
            </div>
          </div>
        )}

        {/* save */}
        <div className="mt-4 flex items-center gap-2.5">
          <button
            onClick={save}
            disabled={syms.length === 0}
            className={cn(
              "inline-flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-3 text-[13px] font-semibold text-primary-foreground transition-all disabled:opacity-45",
              saved ? "bg-accent-tertiary-dark" : "bg-primary"
            )}
          >
            {saved ? <Check className="size-4" /> : <Save className="size-4" />}
            {saved ? "Logged" : "Save today's log"}
          </button>
          <span className={cn("text-[11px] font-semibold text-accent-tertiary-dark transition-opacity", showToast ? "opacity-100" : "opacity-0")}>
            Saved ✓
          </span>
        </div>

        {saved && (
          <div className="mt-3.5 rounded-2xl border border-border bg-card p-4" style={{ animation: "cardBounce 700ms var(--spring) both" }}>
            <div className="mb-1 flex items-center gap-1.5 text-[14px] font-medium text-primary">
              <Sparkles className="size-4 text-accent-primary-dark" /> Your engine is learning
            </div>
            <div className="text-[12px] leading-relaxed text-muted-foreground">
              After 5 logs we start showing your pattern. After 30, your forecast adapts to your specific triggers.
            </div>
          </div>
        )}
      </div>

      {/* burst fx */}
      <div className="pointer-events-none absolute inset-0 z-[5]">
        {fx.map((p) => <Burst key={p.id} x={p.x} y={p.y} />)}
      </div>
    </Screen>
  );
}

function Burst({ x, y }: { x: number; y: number }) {
  const pal = ["var(--accent-primary)", "var(--accent-primary-dark)", "var(--accent-secondary)", "var(--accent-tertiary)"];
  const burst = Array.from({ length: 8 }).map((_, i) => {
    const ang = (i / 8) * Math.PI * 2;
    return { bx: `${Math.cos(ang) * 32}px`, by: `${Math.sin(ang) * 32}px`, c: pal[i % 4] };
  });
  return (
    <div style={{ position: "absolute", left: x, top: y }}>
      {burst.map((b, i) => (
        <span key={i} className="burst" style={{ background: b.c, ["--bx" as string]: b.bx, ["--by" as string]: b.by, animation: "burstOut 600ms ease-out forwards" }} />
      ))}
      <span className="floatup-p" style={{ left: -6, color: "var(--accent-primary-dark)" }}>♥</span>
    </div>
  );
}
