# 05 — Patterns Screen

**Purpose:** turn the user's logged history into personal insights — "your itchy
days cluster on high-humidity afternoons" — with a % match, a mini chart, and an
actionable follow-up.

> Reference: `GET /v2/patterns` in
> `reference/engine/engagement_service/engagement_api.py`.

---

## Gate: need ≥ 5 logs

Patterns don't unlock until the user has logged enough to be meaningful.

```python
if len(logs) < 5:
    return {"ready": False, "logs_needed": 5 - len(logs),
            "message": f"{len(logs)}/5 logs — keep logging to unlock patterns"}
```

---

## The miner (symptom ↔ environment co-occurrence)

The reference mines **per-symptom co-occurrence with high humidity**. This works
precisely because each log snapshotted its environment bands at write time
(doc 02).

```python
HUMID_HIGH = {"High", "Very High", "Extreme"}   # humidity bands that count

by_symptom = group logs by symptom
for symptom, ls in by_symptom:
    if len(ls) < 3:                              # need ≥3 of that symptom
        continue
    hits  = count(l for l in ls if l.humidity_band in HUMID_HIGH)
    match = round(100 * hits / len(ls))          # % of this symptom's days that were humid
    if match >= 60:                              # only surface strong patterns
        emit({ "pattern": f"'{symptom}' clusters on high-humidity days",
               "match_pct": match, "n": len(ls), "driver": "Humidity" })
sort patterns by match_pct desc
```

### Generalising to all drivers (production target)

The reference only checks Humidity. Generalise the same shape to every driver so
you can surface UV/AQI/Temperature patterns too:

```python
for symptom, ls in by_symptom:
    if len(ls) < 3: continue
    for driver, harmful_bands in HARMFUL.items():     # UV, AQI, Temp, Humidity
        hits  = count(l for l in ls if l.band[driver] in harmful_bands)
        match = round(100 * hits / len(ls))
        if match >= 60:
            emit(symptom, driver, match, n=len(ls))
keep top 3 by match_pct
```
`HARMFUL` = the low-points bands per factor (e.g. UV ∈ {Very High, Extreme},
AQI ∈ {Poor, Very Poor, Severe}, Temp ∈ {Hot, Extreme Heat, Cold, Extreme Cold}).

> The match % is a **real co-occurrence rate** — the share of a symptom's logged
> days that fell on a harmful-band day for that driver. The prototype's 83/71/68
> ribbons were decorative placeholders; replace them with this computed value.

### Optional weekday/sleep patterns

The "best window: weekends" card needs sleep/weekday data the current logs don't
carry. Only surface it if you add those signals; otherwise omit. Don't fabricate.

---

## Endpoint contract

`GET /v2/patterns?user_id=…`

Not ready:
```json
{ "ready": false, "logs_needed": 2, "message": "3/5 logs — keep logging to unlock patterns" }
```
Ready:
```json
{
  "ready": true, "n_logs": 47,
  "patterns": [
    { "pattern": "'itchy' clusters on high-humidity days", "match_pct": 83, "n": 12, "driver": "Humidity" },
    { "pattern": "'breakout' clusters on high-AQI mornings", "match_pct": 68, "n": 9, "driver": "AQI" }
  ]
}
```

---

## Edge cases

- **< 3 of any one symptom** — skip that symptom (not enough signal).
- **No pattern ≥ 60%** — return `ready:true, patterns:[]`; the UI shows a "keep
  logging" state rather than weak/false patterns.
- **Correlation ≠ causation** — copy stays observational ("clusters on…"), never
  prescriptive. Honour the locked voice (no "advice").
