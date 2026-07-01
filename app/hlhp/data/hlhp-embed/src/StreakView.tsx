import type { StreakData } from "./App";
import { DONE, MISSED, RING } from "./App";

function dayNum(iso: string) {
  return parseInt(iso.slice(-2), 10) || 0;
}

export function StreakView({ data }: { data: StreakData | null }) {
  const streak = data?.current_streak ?? 0;
  const grid = data?.week_grid ?? [];
  const toNext = data?.days_to_next_badge ?? (streak < 7 ? 7 - streak : streak < 30 ? 30 - streak : 0);

  return (
    <div style={{ padding: "20px 24px", textAlign: "center" }}>
      <div className="flame-stack" style={{ position: "relative", width: 150, height: 188, margin: "0 auto" }}>
        <div className="flame-anim" style={{ position: "absolute", inset: 0, animation: "flameFlicker 1.8s ease-in-out infinite", transformOrigin: "center bottom" }}>
          <svg width="150" height="188" viewBox="0 0 160 200" aria-hidden>
            <path d="M 80 180 Q 30 150 40 100 Q 50 70 65 80 Q 60 50 80 30 Q 100 50 95 80 Q 110 70 120 100 Q 130 150 80 180 Z" fill="var(--hlhp-flame-mid)" opacity="0.95" />
            <path d="M 80 175 Q 45 150 55 110 Q 65 85 80 90 Q 80 65 95 95 Q 110 110 115 150 Q 105 170 80 175 Z" fill="var(--hlhp-flame)" />
            <path d="M 80 170 Q 60 155 65 130 Q 75 110 80 115 Q 85 105 95 130 Q 100 155 80 170 Z" fill="var(--hlhp-flame-core)" />
          </svg>
        </div>
        <span
          className="hlhp-streak-count"
          data-streak-count
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 26,
            zIndex: 3,
            textAlign: "center",
            display: "inline-block",
            whiteSpace: "nowrap",
            lineHeight: 1,
            fontSize: 32,
            fontWeight: 600,
            color: "#fff",
            textShadow: "0 2px 4px rgba(0,0,0,.35)",
          }}
        >
          {streak}
        </span>
      </div>

      <div style={{ marginTop: -6, fontSize: 12, fontWeight: 500, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--muted-foreground)" }}>
        days strong
      </div>

      <div className="day-grid" style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 8, marginTop: 18 }}>
        {grid.map((d, i) => (
          <div
            key={d.date}
            className={`day-dot ${d.done ? "done" : "missed"}${d.today ? " today" : ""}`}
            data-hlhp-day-dot
            data-done={d.done ? "true" : "false"}
            data-today={d.today ? "true" : "false"}
            style={{
              aspectRatio: "1",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 10,
              fontWeight: 600,
              color: "#fff",
              background: d.done ? DONE : MISSED,
              boxShadow: d.today ? RING : undefined,
              animation: `dotPop 400ms var(--spring) ${i * 60}ms both`,
            }}
          >
            {dayNum(d.date)}
          </div>
        ))}
      </div>

      <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 12, background: "#fff7ed", fontSize: 12, textAlign: "left" }}>
        {toNext > 0
          ? `${toNext} days to your ${streak < 7 ? "7" : "30"}-day badge`
          : "Badge unlocked"}
        <div style={{ fontSize: 10, color: "var(--muted-foreground)", marginTop: 4 }}>Only 3% of users reach 30 days</div>
      </div>
    </div>
  );
}
