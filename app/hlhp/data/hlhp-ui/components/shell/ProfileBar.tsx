"use client";

import { useHlhp } from "@/lib/store";
import { allCities } from "@/lib/evidence";

/**
 * Profile bar — city × skin × concern selectors. Changing any one recomputes
 * the SFI, mode, flash alert and impact lines from the REAL scenario library
 * for that combination (turns the demo into a live library browser).
 */
export function ProfileBar() {
  const { evidence, profile, setProfile } = useHlhp();
  if (!evidence) return null;

  const cities = allCities(evidence);
  const sel =
    "appearance-none cursor-pointer rounded-lg border border-border bg-card py-[5px] pl-[9px] pr-6 text-[11px] text-primary focus:border-accent-primary focus:outline-none";

  return (
    <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto border-b border-border/70 bg-accent-secondary/[0.07] px-3 py-2">
      <span className="mr-0.5 whitespace-nowrap text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
        Profile
      </span>
      <select className={sel} value={profile.city} onChange={(e) => setProfile({ city: e.target.value })} title="City">
        {cities.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      <select className={sel} value={profile.skin} onChange={(e) => setProfile({ skin: e.target.value })} title="Skin type">
        {evidence.skins.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <select className={sel} value={profile.concern} onChange={(e) => setProfile({ concern: e.target.value })} title="Main concern">
        {evidence.concerns.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
    </div>
  );
}
