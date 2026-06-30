"use client";

import { useMemo } from "react";
import { useReducedMotion } from "@/lib/hooks";

/**
 * components/anim/Particles.tsx — reusable decorative particle layers ported
 * from the prototype. All recolored to brand tokens. Each is absolutely
 * positioned to fill its relative parent; pointer-events: none.
 *
 * Skipped entirely under prefers-reduced-motion.
 */

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

/**
 * Brand confetti/particle palette — token-driven, NO amber/cream.
 * Pulls from the SkinBB ramp (indigo, periwinkle, lavender, lime) so every
 * particle stays on-palette. Surge red is reserved for the Surge tab only and
 * is intentionally excluded from celebratory confetti.
 */
const BRAND_PARTICLES = [
  "var(--primary)",
  "var(--accent-primary)",
  "var(--accent-primary-dark)",
  "var(--accent-secondary)",
  "var(--accent-tertiary)",
  "var(--accent-tertiary-dark)",
];
/**
 * Flame embers — the ONE warm-amber moment in the app (Streak tab only),
 * matching the approved `--hlhp-flame*` ramp on the flame itself.
 */
const FLAME_EMBERS = ["var(--hlhp-flame-core)", "var(--hlhp-flame)", "var(--hlhp-flame-mid)"];
export { BRAND_PARTICLES, FLAME_EMBERS };

/** Drifting rain-ish particles (Hello / Log ambient). */
export function DriftParticles({ count = 14, color = "var(--accent-primary-dark)" }: { count?: number; color?: string }) {
  const reduced = useReducedMotion();
  const items = useMemo(
    () =>
      Array.from({ length: count }).map(() => ({
        left: `${rand(0, 100)}%`,
        dx: `${rand(-30, 30)}px`,
        dur: rand(6, 12),
        delay: rand(-10, 0),
        scale: rand(0.6, 1.2),
      })),
    [count]
  );
  if (reduced) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {items.map((p, i) => (
        <span
          key={i}
          className="particle"
          style={{
            left: p.left,
            bottom: 0,
            ["--dx" as string]: p.dx,
            background: `color-mix(in oklch, ${color} 40%, transparent)`,
            animationDuration: `${p.dur}s`,
            animationDelay: `${p.delay}s`,
            transform: `scale(${p.scale})`,
          }}
        />
      ))}
    </div>
  );
}

/** Ember particles rising from the flame (Streak). */
export function EmberParticles({ count = 16 }: { count?: number }) {
  const reduced = useReducedMotion();
  const items = useMemo(
    () =>
      Array.from({ length: count }).map(() => ({
        left: `${rand(35, 65)}%`,
        bottom: `${rand(10, 40)}px`,
        dx: `${rand(-24, 24)}px`,
        dur: rand(1.8, 3.2),
        delay: rand(0, 2.4),
        color: FLAME_EMBERS[Math.floor(rand(0, FLAME_EMBERS.length))],
      })),
    [count]
  );
  if (reduced) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {items.map((p, i) => (
        <span
          key={i}
          className="ember-p"
          style={{
            left: p.left,
            bottom: p.bottom,
            ["--dx" as string]: p.dx,
            background: p.color,
            animationDuration: `${p.dur}s`,
            animationDelay: `${p.delay}s`,
          }}
        />
      ))}
    </div>
  );
}

/** Twinkling sparkles (Share card bg). */
export function Sparkles({ count = 14 }: { count?: number }) {
  const reduced = useReducedMotion();
  const items = useMemo(
    () =>
      Array.from({ length: count }).map(() => ({
        left: `${rand(2, 96)}%`,
        top: `${rand(2, 96)}%`,
        dur: rand(1.4, 2.6),
        delay: rand(0, 2),
        size: rand(6, 12),
      })),
    [count]
  );
  if (reduced) return null;
  return (
    <>
      {items.map((p, i) => (
        <svg
          key={i}
          className="sparkle-p"
          width={p.size}
          height={p.size}
          viewBox="0 0 12 12"
          style={{ left: p.left, top: p.top, animationDuration: `${p.dur}s`, animationDelay: `${p.delay}s` }}
        >
          <path d="M6 0 L7 5 L12 6 L7 7 L6 12 L5 7 L0 6 L5 5 Z" fill="rgba(255,255,255,0.9)" />
        </svg>
      ))}
    </>
  );
}

/**
 * Confetti — a one-shot burst. `runKey` re-triggers it. Used by Recap stamp,
 * Share-on-tap, and Good Day rain (set `count` high + `rain` for full-screen).
 */
export function Confetti({ runKey = 0, count = 40 }: { runKey?: number; count?: number }) {
  const reduced = useReducedMotion();
  const items = useMemo(
    () =>
      Array.from({ length: count }).map(() => ({
        left: `${rand(0, 100)}%`,
        top: `${rand(-10, 10)}%`,
        cx: `${rand(-60, 60)}px`,
        dur: rand(1.4, 2.6),
        delay: rand(0, 0.5),
        rot: rand(0, 360),
        color: BRAND_PARTICLES[Math.floor(rand(0, BRAND_PARTICLES.length))],
        w: rand(6, 10),
        h: rand(8, 14),
      })),
    [count, runKey]
  );
  if (reduced) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {items.map((p, i) => (
        <span
          key={i}
          className="confetti-p"
          style={{
            left: p.left,
            top: p.top,
            width: p.w,
            height: p.h,
            background: p.color,
            borderRadius: 2,
            ["--cx" as string]: p.cx,
            transform: `rotate(${p.rot}deg)`,
            animation: `confettiFall ${p.dur}s ${p.delay}s ease-in forwards`,
          }}
        />
      ))}
    </div>
  );
}
