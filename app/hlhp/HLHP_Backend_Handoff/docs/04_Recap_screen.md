# 04 — Recap Screen

**Purpose:** a 30-day look-back. A colour-coded day strip (coloured by what drove
each day), surge/event callouts, a monthly verdict, and aggregate stats. Feeds the
Share card too.

> Reference: `GET /v2/recap` + `_series()` in
> `reference/engine/engagement_service/engagement_api.py`.

---

## The daily SFI series (`daily_sfi`)

Recap reads a **per-user, per-day SFI time series**. Each day the user checks in
or logs, the day's SFI is written (doc 01/02). Days with no entry are `null`
(rendered as gaps).

```python
def series(user_id, days=30):
    out = []
    for i in range(days-1, -1, -1):          # oldest → newest
        d = today() - i days
        out.append({"date": d, "sfi": DAILY[user_id].get(d, {}).get("sfi")})  # None if absent
    return out
```

> **Production:** populate `daily_sfi` with a **daily cron** that scores every
> active user from that day's actual weather, in addition to on-demand writes
> when the user opens the app or logs. That keeps the series dense even on days
> the user didn't open the app. (The demo synthesises history; production must
> store it.)

### Driver colour per day

Each day mark is coloured by the **dominant driver** that day (the factor with
the lowest band points — doc 01 §3). Store the driver alongside the SFI:

| Driver | Colour | Token |
|---|---|---|
| Comfort (no harmful factor / SFI high) | green | `--drv-comfort` |
| Humidity | blue | `--drv-humidity` |
| UV | red | `--drv-uv` |
| Heat (Temperature) | orange | `--drv-temp` |
| AQI | purple | `--drv-aqi` |

So `daily_sfi` rows should carry `{date, sfi, personal_sfi, band, driver}`.

---

## Aggregates

```
avg_sfi      = round(mean(sfi for days where sfi is not null))
logged_days  = count(days where sfi is not null)
surge_days   = count(log events where sfi < 45)        # reference threshold
trend_vs_prev (Share/weekly-card) = avg(last 7) − avg(previous 7)
```
The reference `surge_days` counts **log events** below 45; an alternative is to
count **days** whose stored SFI < 45 — pick one and document it.

### Verdict (monthly narrative)

The "Stronger than May" verdict compares this period's `avg_sfi` to the prior
period's. Compose: `headline` (this avg vs last avg, up/down), `sub`
(`Avg SFI {avg} (was {prev}) · {dropped} dropped days`). Reference content comes
from `GET /catchup`/`/v2/recap`.

### Event callouts

Surface the notable sudden events in the window (heat wave, humidity wave, dust
spike), each with its date, the SFI drop (`from → to`), and the driver colour.
Derive these from days where the day-over-day SFI fell sharply or a band crossed
into a harmful range. The demo hard-codes 2–3; production should detect them from
the series + band history.

---

## Endpoint contract

`GET /v2/recap?user_id=…&days=30`

```json
{
  "days": 30,
  "avg_sfi": 68,
  "logged_days": 28,
  "surge_days": 2,
  "series": [ {"date":"2026-06-01","sfi":71,"driver":"comfort"}, {"date":"2026-06-02","sfi":null,"driver":null}, … ],
  "events": [ {"date":"2026-06-12","driver":"temp","from":78,"to":54}, … ],
  "verdict": { "headline":"Stronger than May", "sub":"Avg SFI 68 (was 61) · 0 dropped days" }
}
```
(`driver`, `events`, `verdict` extend the reference shape — add them.)

---

## Edge cases

- **Sparse history (new user)** — return the series with `null`s; the UI pads/
  greys missing days. `avg_sfi` over an empty set → `null`.
- **`days` param** — support 7/15/30; Share uses the last 7 of the same series.
- **Backfill** — recompute aggregates from stored rows; don't cache stale averages.
