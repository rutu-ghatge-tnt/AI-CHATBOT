"use client";

import { useHlhp } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Onboarding overlay — bobble mascot, consent CTA. "Let's begin" records
 * consent (mock POST /consent) + sets localStorage; "Skip" sets localStorage
 * only. Fades over the frame.
 */
export function Onboarding() {
  const { onboardingDone, completeOnboarding, skipOnboarding } = useHlhp();

  return (
    <div
      className={cn(
        "absolute inset-0 z-[100] flex items-center justify-center p-8 transition-opacity duration-500",
        onboardingDone ? "pointer-events-none opacity-0" : "opacity-100"
      )}
      style={{ background: "rgba(26,43,71,0.96)" }}
      aria-hidden={onboardingDone}
    >
      <div className="max-w-[320px] text-center text-white">
        <div className="mx-auto" style={{ width: 140, height: 160, animation: "bobble 2400ms ease-in-out infinite" }}>
          <svg width="140" height="160" viewBox="0 0 140 160" aria-hidden="true">
            <ellipse cx="70" cy="100" rx="44" ry="34" fill="#FFFFFF" stroke="#E5D9BD" />
            <circle cx="28" cy="96" r="11" fill="#FFFFFF" stroke="#E5D9BD" />
            <circle cx="112" cy="96" r="11" fill="#FFFFFF" stroke="#E5D9BD" />
            <circle cx="70" cy="68" r="14" fill="#FFFFFF" stroke="#E5D9BD" />
            <ellipse cx="60" cy="72" rx="10" ry="13" fill="#3F3530" />
            <ellipse cx="80" cy="72" rx="10" ry="13" fill="#3F3530" />
            <circle cx="60" cy="69" r="2.2" fill="#FFFFFF" />
            <circle cx="80" cy="69" r="2.2" fill="#FFFFFF" />
            <path d="M 62 82 Q 70 88 78 82" stroke="#3F3530" strokeWidth="2" fill="none" strokeLinecap="round" />
          </svg>
        </div>
        <h2 className="mt-4 font-holiday text-[22px] font-semibold">Meet your skin coach</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-white/80">
          I learn your skin&apos;s patterns across humidity, UV, sleep, and pollution — then quietly tell you what
          matters, only when it actually does. Information, never noise.
        </p>
        <div className="mt-5 flex flex-col items-center gap-2.5">
          <Button color="warmth" rounded="full" onClick={completeOnboarding} className="bg-hlhp-sun text-primary">
            Let&apos;s begin
          </Button>
          <button onClick={skipOnboarding} className="text-[11px] text-white/50 hover:text-white/70">
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}
