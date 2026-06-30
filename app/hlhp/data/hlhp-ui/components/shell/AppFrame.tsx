"use client";

import { useHlhp } from "@/lib/store";
import { Toolbar } from "./Toolbar";
import { Tabs } from "./Tabs";
import { ProfileBar } from "./ProfileBar";
import { BadgeStrip } from "./BadgeStrip";
import { CoachBubble } from "./CoachBubble";
import { Onboarding } from "./Onboarding";

import { HelloScreen } from "@/components/screens/HelloScreen";
import { LogScreen } from "@/components/screens/LogScreen";
import { StreakScreen } from "@/components/screens/StreakScreen";
import { RecapScreen } from "@/components/screens/RecapScreen";
import { PatternsScreen } from "@/components/screens/PatternsScreen";
import { ShareScreen } from "@/components/screens/ShareScreen";
import { LearnScreen } from "@/components/screens/LearnScreen";

/**
 * The ~440px rounded mobile frame; assembles shell + active screen.
 * v2 tabs: Hello · Log · Streak · Recap · Patterns · Share · Learn
 * (Surge folded into Hello; Good Day replaced by Learn.)
 */
export function AppFrame() {
  const { tab, surge } = useHlhp();

  return (
    <div className="flex min-h-dvh items-center justify-center p-4 sm:p-6">
      <div
        id="hlhp-frame"
        className="relative w-full max-w-[440px] overflow-hidden rounded-[28px] shadow-[0_20px_60px_rgba(0,0,0,0.12)]"
        style={{
          background: "var(--background)",
          // a surge shake is triggered imperatively from HelloScreen via this id
          animation: undefined,
        }}
        data-surge={surge ? "1" : "0"}
      >
        <Onboarding />
        <Toolbar />
        <ProfileBar />
        <Tabs />
        <BadgeStrip />
        <CoachBubble />

        <div>
          {tab === "s0" && <HelloScreen />}
          {tab === "s1" && <LogScreen />}
          {tab === "s2" && <StreakScreen />}
          {tab === "s4" && <RecapScreen />}
          {tab === "sp" && <PatternsScreen />}
          {tab === "sc" && <ShareScreen />}
          {tab === "sl" && <LearnScreen />}
        </div>
      </div>
    </div>
  );
}
