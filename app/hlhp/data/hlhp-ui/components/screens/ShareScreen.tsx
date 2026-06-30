"use client";

import { useEffect, useState } from "react";
import { TrendingUp, Instagram, MessageCircle, Download, Copy } from "lucide-react";
import { useHlhp } from "@/lib/store";
import { Screen } from "@/components/shell/ScreenShell";
import { Sparkles as SparkleLayer, Confetti } from "@/components/anim/Particles";
import { Mascot } from "@/components/anim/Mascot";
import { useCountUp, useReplay } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { SHARE_HEADLINE, SHARE_SUB, SHARE_CAPTION } from "@/mock/content";

/**
 * SC — Share. Big number = week avg SFI (from /history trend); 7 bars from the
 * last 7 trend points; trend pill from weekly delta. Share buttons toast only.
 * Animations: big-number count-up, chart bars scaleY, sparkles, mascot pop,
 * confetti burst on share tap.
 */
export function ShareScreen() {
  const { history, sfx } = useHlhp();
  const [rk, replay] = useReplay();
  const [confettiKey, setConfettiKey] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const [copyLabel, setCopyLabel] = useState("Copy");

  function copyCaption() {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(SHARE_CAPTION).catch(() => {});
    }
    sfx("pop");
    setCopyLabel("Copied!");
    setTimeout(() => setCopyLabel("Copy"), 1600);
  }

  const last7 = (history?.trend ?? []).slice(-7);
  const vals = last7.map((t) => t.sfi).filter((v): v is number => v != null);
  const weekAvg = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : (history?.sfi_average ?? 68);
  const num = useCountUp(shown ? weekAvg : 0, 900, rk);

  // prev week delta (rough): compare to days -14..-8
  const prev = (history?.trend ?? []).slice(-14, -7).map((t) => t.sfi).filter((v): v is number => v != null);
  const prevAvg = prev.length ? Math.round(prev.reduce((a, b) => a + b, 0) / prev.length) : weekAvg - 4;
  const delta = weekAvg - prevAvg;

  useEffect(() => {
    setShown(false);
    const t = setTimeout(() => setShown(true), 150);
    return () => clearTimeout(t);
  }, [rk]);

  function onShare(kind: string) {
    sfx("celebrate");
    setConfettiKey((k) => k + 1);
    setToast(kind === "save" ? "Saved to your device" : kind === "wa" ? "Ready to share on WhatsApp" : "Ready for your Story");
    setTimeout(() => setToast(null), 1800);
  }

  const barColors = ["var(--hlhp-warmth)", "var(--accent-primary)", "var(--accent-primary-dark)", "var(--hlhp-good)", "var(--accent-primary)", "var(--hlhp-warmth)", "var(--hlhp-good-deep)"];

  return (
    <Screen noPad className="bg-primary">
      {/* the shareable card */}
      <div className="relative aspect-[9/16] max-h-[560px] overflow-hidden p-5 text-white" style={{ background: "linear-gradient(160deg, var(--accent-primary-dark) 0%, var(--primary) 55%, color-mix(in oklch, var(--primary) 80%, black) 100%)" }} key={rk}>
        <SparkleLayer count={14} />
        <Confetti runKey={confettiKey} count={36} />

        <div className="relative flex items-center justify-between">
          <div className="text-[10px] font-bold tracking-[0.2em] opacity-60">MY SFI WEEK</div>
          <div className="text-[11px] opacity-70">This week</div>
        </div>

        <div className="relative mt-7 text-[76px] font-bold leading-none" style={{ opacity: shown ? 1 : 0, transform: shown ? "scale(1)" : "scale(0.5)", transition: "all 800ms var(--spring)" }}>
          {num}
          <span className="ml-1 align-top text-[16px] opacity-60">/100</span>
        </div>

        <div className="mt-1.5">
          <span className="inline-flex items-center gap-1 rounded-full bg-hlhp-good/25 px-2.5 py-1 text-[13px] font-semibold text-hlhp-good" style={{ opacity: shown ? 1 : 0, transform: shown ? "translateY(0)" : "translateY(10px)", transition: "all 500ms ease 600ms" }}>
            <TrendingUp className="size-3.5" /> {delta >= 0 ? "+" : ""}{delta} from last week
          </span>
        </div>

        {/* mini chart */}
        <div className="mt-6 flex h-[70px] items-end gap-1.5">
          {last7.map((t, i) => {
            const h = ((t.sfi ?? 40) / 100) * 100;
            return (
              <div key={t.date} className="flex-1 rounded-t origin-bottom" style={{ height: `${h}%`, background: barColors[i % barColors.length], transform: shown ? "scaleY(1)" : "scaleY(0)", transition: `transform 600ms var(--spring) ${i * 60}ms` }} />
            );
          })}
        </div>
        <div className="mt-1 flex justify-between text-[10px] opacity-60"><span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span><span>S</span></div>

        <div className="mt-4 font-holiday text-[19px] font-semibold leading-tight" style={{ opacity: shown ? 1 : 0, transform: shown ? "translateY(0)" : "translateY(10px)", transition: "all 600ms var(--spring) .3s" }}>
          {SHARE_HEADLINE}
        </div>
        <div className="mt-3 text-[12.5px] leading-relaxed" style={{ opacity: shown ? 0.92 : 0, transition: "opacity 500ms ease 700ms" }}>
          {SHARE_SUB}
        </div>

        <Mascot mood="radiant" size={48} className="absolute right-4 top-4" />
        <div className="absolute bottom-4 left-5 text-[10px] font-medium tracking-wide opacity-70">Apply Knowledge to the Skin</div>
        <div className="absolute bottom-4 right-5 text-[10px] tracking-wide opacity-60">@skinbb</div>

        {toast && (
          <div className="absolute bottom-12 left-1/2 z-20 -translate-x-1/2 rounded-full bg-white/95 px-4 py-1.5 text-[11px] font-medium text-primary shadow-lg">
            {toast}
          </div>
        )}
      </div>

      {/* copyable caption */}
      <div className="mx-3.5 mb-3.5 rounded-xl border border-border bg-card p-3">
        <div className="mb-1.5 flex items-center justify-between text-[9px] font-medium uppercase tracking-wider text-muted-foreground">
          <span>Caption — ready to paste</span>
          <button onClick={copyCaption} className="flex items-center gap-1 text-[10px] font-semibold text-accent-primary-dark">
            <Copy className="size-3" /> {copyLabel}
          </button>
        </div>
        <div className="whitespace-pre-wrap text-[11.5px] leading-relaxed text-secondary-foreground">{SHARE_CAPTION}</div>
      </div>

      {/* share row */}
      <div className="flex gap-2 bg-primary p-3.5">
        <ShareBtn onClick={() => onShare("insta")} className="bg-accent-primary-dark"><Instagram className="size-4" /> Story</ShareBtn>
        <ShareBtn onClick={() => onShare("wa")} className="bg-hlhp-good-deep"><MessageCircle className="size-4" /> WhatsApp</ShareBtn>
        <ShareBtn onClick={() => onShare("save")} className="bg-accent-secondary-dark"><Download className="size-4" /> Save</ShareBtn>
      </div>

      <div className="flex justify-center bg-primary pb-3">
        <button onClick={replay} className="text-[10px] uppercase tracking-wider text-white/40 hover:text-white/70">Replay</button>
      </div>
    </Screen>
  );
}

function ShareBtn({ children, onClick, className }: { children: React.ReactNode; onClick: () => void; className?: string }) {
  return (
    <button onClick={onClick} className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-[10px] py-2.5 text-[11px] font-medium text-white", className)}>
      {children}
    </button>
  );
}
