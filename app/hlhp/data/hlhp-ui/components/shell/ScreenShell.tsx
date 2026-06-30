"use client";

import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

/** The replay bar shown at the top of most screens. */
export function ReplayBar({
  label,
  onReplay,
  light = false,
}: {
  label: string;
  onReplay: () => void;
  light?: boolean;
}) {
  return (
    <div className="relative z-[3] flex items-center justify-between py-2 pb-3.5">
      <span
        className={cn(
          "text-[11px] font-medium uppercase tracking-wider",
          light ? "text-white/90 [text-shadow:0_1px_4px_rgba(0,0,0,0.2)]" : "text-muted-foreground"
        )}
      >
        {label}
      </span>
      <button
        onClick={onReplay}
        className={cn(
          "flex items-center gap-1 rounded-lg border px-3 py-1.5 text-[11px] transition-colors",
          light
            ? "border-white/40 bg-white/90 text-primary"
            : "border-border text-primary hover:bg-accent-primary/5"
        )}
        aria-label="Replay animation"
      >
        <RefreshCw className="size-3.5" />
      </button>
    </div>
  );
}

/**
 * Screen wrapper — applies the fadeSlide entrance and the consistent padding.
 * `stageClassName` carries the per-screen ambient background gradients.
 */
export function Screen({
  children,
  stageClassName,
  className,
  noPad = false,
}: {
  children: React.ReactNode;
  stageClassName?: string;
  className?: string;
  noPad?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative min-h-[540px] overflow-hidden",
        noPad ? "" : "px-6 pb-6 pt-5",
        stageClassName,
        className
      )}
      style={{ animation: "fadeSlide 500ms var(--spring)" }}
    >
      {children}
    </div>
  );
}
