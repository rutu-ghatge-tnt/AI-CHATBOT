"use client";

import { useHlhp } from "@/lib/store";
import { TABS } from "@/lib/tabs";
import { cn } from "@/lib/utils";

/** 8-tab strip. Active tab fetches nothing extra except Surge (handled in screen). */
export function Tabs() {
  const { tab, setTab, sfx } = useHlhp();
  return (
    <div className="no-scrollbar flex gap-0.5 overflow-x-auto border-b border-border/70 px-1.5 pt-2">
      {TABS.map((t) => {
        const active = tab === t.id;
        const Icon = t.icon;
        return (
          <button
            key={t.id}
            data-screen={t.id}
            onClick={() => {
              setTab(t.id);
              sfx("whoosh");
            }}
            className={cn(
              "min-w-[48px] flex-1 rounded-t-lg px-1 py-2 text-center text-[9px] font-medium tracking-wide transition-all",
              active
                ? "bg-card text-primary shadow-[0_-2px_6px_rgba(0,0,0,0.04)]"
                : "text-muted-foreground hover:text-primary"
            )}
          >
            <Icon className="mx-auto mb-0.5 size-4" />
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
