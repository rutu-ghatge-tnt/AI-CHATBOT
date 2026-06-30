"use client";

import type { MascotMood } from "@/api/types";

/**
 * components/anim/Mascot.tsx — the HLHP coach blob, ported from the prototype's
 * inline SVGs and parameterized by mood + size. One source of truth instead of
 * five copies. Eyes/mouth/brows shift with mood; optional waving hand & crown.
 *
 * Colors use the cream/ink palette via tokens so it reads on brand.
 */

interface MascotProps {
  mood?: MascotMood;
  size?: number;
  wave?: boolean;       // waving hand (Hello)
  crown?: boolean;      // celebration stars (Good Day)
  worried?: boolean;    // worry brows (Surge)
  className?: string;
  celebrate?: boolean;  // celebJump loop
}

export function Mascot({
  mood = "happy",
  size = 100,
  wave = false,
  crown = false,
  worried = false,
  className,
  celebrate = false,
}: MascotProps) {
  const h = Math.round(size * 1.1);
  // mouth path varies by mood
  const happy = mood === "radiant" || mood === "happy";
  const tense = mood === "concerned" || mood === "stressed" || mood === "alarmed" || worried;
  const mouth = happy
    ? "M 42 56 Q 50 64 58 56"        // smile
    : tense
    ? "M 43 60 Q 50 55 57 60"        // worried
    : "M 44 58 Q 50 60 56 58";       // neutral

  return (
    <div
      className={className}
      style={celebrate ? { animation: "celebJump 1.4s ease-in-out infinite" } : undefined}
    >
      <svg width={size} height={h} viewBox="0 0 100 110" aria-hidden="true">
        {/* body */}
        <ellipse cx="50" cy="70" rx="32" ry="24" fill="#FFFFFF" stroke="#E5D9BD" />
        <circle cx="22" cy="66" r="9" fill="#FFFFFF" stroke="#E5D9BD" />
        <circle cx="78" cy="66" r="9" fill="#FFFFFF" stroke="#E5D9BD" />
        {/* head */}
        <circle cx="50" cy="44" r="12" fill="#FFFFFF" stroke="#E5D9BD" />
        {/* eyes */}
        <ellipse cx="42" cy="48" rx="9" ry="11" fill="#3F3530" />
        <ellipse cx="58" cy="48" rx="9" ry="11" fill="#3F3530" />
        <circle cx="42" cy="46" r="1.8" fill="#FFFFFF" />
        <circle cx="58" cy="46" r="1.8" fill="#FFFFFF" />
        {/* mouth */}
        <path d={mouth} stroke="#3F3530" strokeWidth="1.8" fill="none" strokeLinecap="round" />
        {/* worry brows */}
        {tense && (
          <>
            <path d="M 33 36 Q 38 31 43 36" stroke="var(--destructive)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
            <path d="M 57 36 Q 62 31 67 36" stroke="var(--destructive)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          </>
        )}
        {/* celebration stars */}
        {crown && (
          <path d="M 40 34 L 43 28 L 46 34 Z M 54 34 L 57 28 L 60 34 Z" fill="var(--accent-secondary)" stroke="var(--accent-primary-dark)" strokeWidth="1" />
        )}
        {/* waving hand */}
        {wave && (
          <g style={{ transformOrigin: "82px 66px", animation: "wave 1.4s ease-in-out infinite" }}>
            <ellipse cx="86" cy="58" rx="6" ry="8" fill="#FFFFFF" stroke="#E5D9BD" />
          </g>
        )}
      </svg>
    </div>
  );
}
