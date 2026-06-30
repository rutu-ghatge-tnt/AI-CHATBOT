# 03 — Streak Screen

**Purpose:** reward daily engagement. Shows the current consecutive-day streak,
a 7-day grid of which days were logged, badges, and the next milestone.

> Reference: `GET /v2/streak` + `_streak()` in
> `reference/engine/engagement_service/engagement_api.py`.

---

## The streak algorithm (canonical)

A day "counts" if the user has **a log OR a check-in** on that local date. The
streak is the count of **consecutive days ending today** that all count.

```python
def streak(user_id):
    # set of dates that count = daily-SFI dates ∪ log dates
    days = set(DAILY[user_id].keys()) | { l["date"] for l in LOGS[user_id] }
    n, d = 0, today()
    while d.isoformat() in days:     # walk backwards from today
        n += 1
        d -= 1 day
    return n
```

Key points:
- **De-duplicated by date** — two logs on the same day still count as one day.
- **Breaks on the first missing day.** Miss a day → streak resets to 0 (or to
  the days since the gap). There is no grace/freeze in the reference; add one only
  if product asks.
- **Today counts** as soon as there is any log or check-in today. Opening the app
  (a check-in that writes the daily SFI) is enough — see doc 01/02 write path.
- **Timezone:** use the **user's local date**, not UTC, so "today" matches what
  the user sees. Store `date` as the local `YYYY-MM-DD`.

---

## Badges (rules)

The reference returns three booleans; the UI shows 7 (4 earned + 3 locked). The
3 real ones the backend must own:

| Badge | Rule (server-authoritative) |
|---|---|
| `first_log` | `len(logs) >= 1` |
| `streak_7` | `current_streak >= 7` |
| `streak_30` | `current_streak >= 30` |

UI-only / decorative (compute client-side or add later, clearly flagged):
`heat_surge` (a sudden-event happened in history), `first_pattern`
(`logs >= 5`), `monsoon`, `diwali`. If product wants these server-side, define
their triggers explicitly.

`days_to_next_badge = (7 − streak) if streak < 7 else (30 − streak) if streak < 30 else 0`.

---

## 7-day grid

For the last 7 local dates ending today, mark each:
- **today** — the current date (highlighted regardless of logged state)
- **done** — a non-today date that has a log/check-in
- **empty** — otherwise

```python
def week_grid(user_id):
    logged = set(DAILY[user_id].keys()) | { l["date"] for l in LOGS[user_id] }
    out = []
    for i in range(6, -1, -1):
        d = today() - i days
        out.append({"date": d, "done": d in logged, "today": i == 0})
    return out
```

---

## Endpoint contract

`GET /v2/streak?user_id=…`

```json
{
  "current_streak": 23,
  "longest_streak": 23,
  "badges": { "first_log": true, "streak_7": true, "streak_30": false },
  "days_to_next_badge": 7,
  "week_grid": [ {"date":"2026-06-24","done":true,"today":false}, … ]
}
```
(`longest_streak` and `week_grid` are UI additions to the reference shape — add
them; both are cheap to compute.)

---

## Edge cases

- **Backfilled logs** (user logs for a past date) — recompute the streak from the
  full date set; backfilling can legitimately extend a streak.
- **Multiple devices / timezones** — anchor on a single stored local date per
  event; don't recompute "today" per request in a different TZ.
- **Cron check-ins** — if a daily-SFI writer cron runs without the user opening
  the app, decide whether that counts as a check-in. Reference treats any
  `daily_sfi` row as a counting day, so a cron WOULD keep the streak alive.
  Product decision — document whichever you choose.
