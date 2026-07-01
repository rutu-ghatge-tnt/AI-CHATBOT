import { useEffect, useState } from "react";
import { StreakView } from "./StreakView";

const DONE = "linear-gradient(135deg, #65a30d, #a3e635)";
const MISSED = "linear-gradient(135deg, #dc2626, #ef4444)";
const RING = "0 0 0 3px rgba(26, 43, 71, 0.35)";

export type WeekDay = { date: string; done: boolean; today?: boolean };

export type StreakData = {
  current_streak: number;
  days_to_next_badge?: number;
  week_grid: WeekDay[];
};

export function App() {
  const [data, setData] = useState<StreakData | null>(null);
  const userId = new URLSearchParams(window.location.search).get("user_id") || "demo-user";

  useEffect(() => {
    fetch(`/api/hlhp/streak?user_id=${encodeURIComponent(userId)}`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setData)
      .catch(() => setData(null));
  }, [userId]);

  return (
    <div style={shell}>
      <header style={header}>
        <span style={{ fontWeight: 600 }}>HLHP Skin Coach</span>
        <span style={badge}>Personalised</span>
      </header>
      <StreakView data={data} />
    </div>
  );
}

const shell: React.CSSProperties = {
  width: "100%",
  maxWidth: 420,
  background: "#fff",
  borderRadius: 20,
  boxShadow: "0 20px 60px rgba(0,0,0,.12)",
  overflow: "hidden",
};

const header: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "12px 16px",
  borderBottom: "1px solid #eee",
  color: "var(--primary)",
};

const badge: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  background: "#e0e7ff",
  color: "#4338ca",
  padding: "3px 8px",
  borderRadius: 999,
};

export { DONE, MISSED, RING };
