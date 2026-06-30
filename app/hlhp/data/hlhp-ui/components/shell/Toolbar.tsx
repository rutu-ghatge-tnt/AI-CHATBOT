"use client";

import { Sparkles, Volume2, VolumeX } from "lucide-react";
import { useHlhp } from "@/lib/store";
import { cn } from "@/lib/utils";

/** Brand + sound toggle. Web Audio SFX engine lives in lib/sound.ts. */
export function Toolbar() {
  const { muted, toggleSound } = useHlhp();
  return (
    <div className="flex items-center justify-between border-b border-border/70 px-4 py-2.5">
      <div className="flex items-center gap-1.5 text-[13px] font-semibold text-primary">
        <Sparkles className="size-4 text-accent-primary-dark" />
        <span className="font-holiday tracking-tight">HLHP</span>
        <span className="ml-1 rounded-full bg-accent-primary-light px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-wider text-accent-primary-dark">
          SFI
        </span>
      </div>
      <button
        onClick={toggleSound}
        className={cn(
          "flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-[11px] transition-colors",
          muted ? "text-muted-foreground" : "text-primary hover:bg-accent-primary/5"
        )}
        aria-pressed={!muted}
        aria-label={muted ? "Sound off" : "Sound on"}
      >
        {muted ? <VolumeX className="size-3.5" /> : <Volume2 className="size-3.5" />}
        {muted ? "sound off" : "sound on"}
      </button>
    </div>
  );
}
